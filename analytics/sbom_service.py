"""
SBOM service using GitHub Dependency Graph API (SPDX) with CycloneDX fallback processing
"""
import logging
import json
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Optional
from django.utils import timezone
import requests

from .models import SBOM, SBOMComponent
from .github_token_service import GitHubTokenService

logger = logging.getLogger(__name__)


class SBOMService:
    """Service for retrieving and processing SBOMs"""
    
    def __init__(self, repository_full_name: str, user_id: int):
        self.repository_full_name = repository_full_name
        self.user_id = user_id
    
    def fetch_github_sbom(self, user_id: int) -> Dict:
        """Fetch SBOM from GitHub Dependency Graph API as SPDX JSON.
        Returns the parsed SBOM document (SPDX or CycloneDX if GitHub returns that).
        """
        logger.info("Fetching SBOM from GitHub API for %s", self.repository_full_name)
        try:
            owner, repo = self.repository_full_name.split('/', 1)
        except ValueError:
            raise ValueError(f"Invalid repository_full_name: {self.repository_full_name}")

        token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
        if not token:
            token = GitHubTokenService._get_user_token(user_id)
        if not token:
            raise RuntimeError("GitHub token not found for SBOM fetch")

        url = f"https://api.github.com/repos/{owner}/{repo}/dependency-graph/sbom"
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
        }

        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 202:
            # GitHub may be generating the SBOM; caller can retry later
            raise RuntimeError("GitHub SBOM generation in progress (202)")
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub SBOM API error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        # Some variants return the SBOM document under 'sbom'
        sbom_doc = data.get('sbom', data)
        if isinstance(sbom_doc, str):
            try:
                sbom_doc = json.loads(sbom_doc)
            except Exception:
                raise RuntimeError("Failed to parse SBOM string from GitHub API")
        return sbom_doc

    def process_spdx_sbom(self, spdx_data: Dict) -> SBOM:
        """Process SPDX 2.3 SBOM from GitHub into our storage schema."""
        logger.info("Processing SPDX SBOM for %s", self.repository_full_name)

        # Metadata
        created_at = spdx_data.get('creationInfo', {}).get('created')
        if created_at:
            # Replace Z with +00:00 for fromisoformat
            ts = created_at.replace('Z', '+00:00')
            try:
                generated_at = datetime.fromisoformat(ts)
                if generated_at.tzinfo is None:
                    generated_at = timezone.make_aware(generated_at)
            except Exception:
                generated_at = timezone.now()
        else:
            generated_at = timezone.now()

        tool_name = 'GitHub Dependency Graph'
        creators = spdx_data.get('creationInfo', {}).get('creators', [])
        for c in creators:
            if isinstance(c, str) and c.startswith('Tool: '):
                tool_name = c.replace('Tool: ', '').strip()
                break

        sbom = SBOM(
            repository_full_name=self.repository_full_name,
            bom_format='SPDX',
            spec_version=spdx_data.get('spdxVersion', 'SPDX-2.3'),
            serial_number=spdx_data.get('documentNamespace') or f"urn:uuid:{self._generate_uuid()}",
            version=1,
            generated_at=generated_at,
            tool_name=tool_name,
            tool_version='unknown',
            component_count=len(spdx_data.get('packages', [])),
            vulnerability_count=0,
            raw_sbom=spdx_data,
        )
        sbom.save()

        # Components mapping
        for pkg in spdx_data.get('packages', []):
            # Resolve purl from externalRefs if present
            purl = None
            for ref in pkg.get('externalRefs', []) or []:
                if ref.get('referenceType') == 'purl' or ref.get('referenceCategory') == 'PACKAGE-MANAGER':
                    purl = ref.get('referenceLocator') or purl
            component = SBOMComponent(
                sbom_id=sbom,
                group=None,
                name=pkg.get('name'),
                version=pkg.get('versionInfo') or 'unknown',
                purl=purl or '',
                bom_ref=pkg.get('SPDXID') or (purl or pkg.get('name')),
                component_type='library',
                scope='required',
                licenses=[{'license': {'id': pkg.get('licenseConcluded')}}] if pkg.get('licenseConcluded') else [],
                hashes=[],
                properties=[],
                evidence={},
                tags=[],
            )
            component.save()

        logger.info("Stored SPDX SBOM: %d components", sbom.component_count)
        return sbom
    
    def _generate_uuid(self) -> str:
        """Generate a UUID for SBOM serial number"""
        import uuid
        return str(uuid.uuid4())
    
    def process_sbom(self, sbom_data: Dict) -> SBOM:
        """
        Process and store SBOM data in MongoDB
        
        Args:
            sbom_data: Raw SBOM data (CycloneDX)
            
        Returns:
            SBOM document
        """
        logger.info(f"Processing SBOM for {self.repository_full_name}")
        
        # Extract metadata
        metadata = sbom_data.get('metadata', {})
        tools = metadata.get('tools', {}).get('components', [])
        tool_info = tools[0] if tools else {}
        
        # Create SBOM document
        # Parse timestamp with timezone awareness
        timestamp_str = metadata.get('timestamp', '')
        if timestamp_str:
            # Handle ISO format with Z suffix
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str.replace('Z', '+00:00')
            generated_at = datetime.fromisoformat(timestamp_str)
            # Ensure timezone awareness
            if generated_at.tzinfo is None:
                generated_at = timezone.make_aware(generated_at)
        else:
            generated_at = timezone.now()
        
        sbom = SBOM(
            repository_full_name=self.repository_full_name,
            bom_format=sbom_data.get('bomFormat'),
            spec_version=sbom_data.get('specVersion'),
            serial_number=sbom_data.get('serialNumber'),
            version=sbom_data.get('version'),
            generated_at=generated_at,
            tool_name=tool_info.get('name', 'unknown'),
            tool_version=tool_info.get('version', 'unknown'),
            component_count=len(sbom_data.get('components', [])),
            raw_sbom=sbom_data
        )
        sbom.save()
        
        # Process components
        for component_data in sbom_data.get('components', []):
            component = SBOMComponent(
                sbom_id=sbom,
                group=component_data.get('group'),
                name=component_data.get('name'),
                version=component_data.get('version'),
                purl=component_data.get('purl'),
                bom_ref=component_data.get('bom-ref'),
                component_type=component_data.get('type'),
                scope=component_data.get('scope', 'required'),
                licenses=component_data.get('licenses', []),
                hashes=component_data.get('hashes', []),
                properties=component_data.get('properties', []),
                evidence=component_data.get('evidence', {}),
                tags=component_data.get('tags', [])
            )
            component.save()
        
        # Vulnerabilities no longer processed (handled by CodeQL)
        sbom.vulnerability_count = 0
        sbom.save()
        
        logger.info(f"Processed SBOM with {sbom.component_count} components and {sbom.vulnerability_count} vulnerabilities")
        return sbom 

    def _parse_timezone_aware_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse a date string and ensure it's timezone-aware
        
        Args:
            date_str: ISO format date string
            
        Returns:
            Timezone-aware datetime object or None if parsing fails
        """
        if not date_str:
            return None
            
        try:
            # Handle ISO format with Z suffix
            if date_str.endswith('Z'):
                date_str = date_str.replace('Z', '+00:00')
            
            parsed_date = datetime.fromisoformat(date_str)
            
            # Ensure timezone awareness
            if parsed_date.tzinfo is None:
                parsed_date = timezone.make_aware(parsed_date)
                
            return parsed_date
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    def _extract_rust_licenses(self, repo_path: str) -> List[Dict]:
        """
        Extract licenses from Rust project using cargo-license
        
        Args:
            repo_path: Path to the Rust repository
            
        Returns:
            List of license information
        """
        try:
            assert_safe_repo_path(repo_path)
            # Check if cargo-license is available
            result = subprocess.run(['cargo', 'license', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("cargo-license not available, skipping Rust license extraction")
                return []
            
            # Run cargo license
            cmd = ['cargo', 'license', '--json', '--direct-deps-only']
            result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.warning(f"cargo-license failed: {result.stderr}")
                return []
            
            # Parse JSON output
            import json
            licenses_data = json.loads(result.stdout)
            
            # Convert to CycloneDX format
            licenses = []
            for item in licenses_data:
                if 'license' in item:
                    licenses.append({
                        'license': {
                            'id': item['license'],
                            'name': item.get('license', 'Unknown')
                        }
                    })
            
            logger.info(f"Extracted {len(licenses)} licenses from Rust project")
            return licenses
            
        except Exception as e:
            logger.error(f"Error extracting Rust licenses: {e}")
            return [] 

    def _assert_safe_repo_path(self, repo_path: str) -> None:
        """Deprecated: Use analytics.sanitization.assert_safe_repo_path instead."""
        assert_safe_repo_path(repo_path)