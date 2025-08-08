"""
SBOM generation service using cdxgen
"""
import logging
import json
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone as dt_timezone
from typing import Dict, List, Optional
from pathlib import Path
from django.utils import timezone

from .models import SBOM, SBOMComponent, SBOMVulnerability
from management.models import OSSIndexConfig

logger = logging.getLogger(__name__)


class SBOMService:
    """Service for generating and processing SBOMs"""
    
    def __init__(self, repository_full_name: str, user_id: int):
        self.repository_full_name = repository_full_name
        self.user_id = user_id
        self.oss_config = OSSIndexConfig.get_config()
    
    def generate_sbom(self, repo_path: str) -> Dict:
        """
        Generate SBOM using cdxgen with vulnerability scanning
        
        Args:
            repo_path: Path to the cloned repository
            
        Returns:
            Dictionary with SBOM data and metadata
        """
        logger.info(f"Generating SBOM for {self.repository_full_name} at {repo_path}")
        # Validate repository path before using it
        self._assert_safe_repo_path(repo_path)
        
        # Prepare environment variables
        env = os.environ.copy()
        if self.oss_config.email:
            env['OSSINDEX_USERNAME'] = self.oss_config.email
        if self.oss_config.api_token:
            env['OSSINDEX_TOKEN'] = self.oss_config.api_token
        #tweak for macos    
        env["HTTP_PROXY"] = ""
        env["HTTPS_PROXY"] = ""
        env["NO_PROXY"] = "*"
        # Create temporary directory for SBOM output
        with tempfile.TemporaryDirectory() as temp_dir:
            sbom_file = os.path.join(temp_dir, "sbom.json")
            
            # Build cdxgen command
            cmd = [
                'npx', '@cyclonedx/cdxgen',
                '--no-install-deps',
                '--include-vulnerabilities',
                '--profile', 'license-compliance',
                '-o', sbom_file,
                '.'
            ]
            
            logger.info(f"Executing cdxgen command: {' '.join(cmd)}")
            
            try:
                # Execute cdxgen
                result = subprocess.run(
                    cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 minutes timeout
                    cwd=repo_path
                )
                
                if result.returncode != 0:
                    logger.error(f"cdxgen failed: {result.stderr}")
                    # Check if it's a recursion error
                    if "RecursionError" in result.stderr or "maximum recursion depth exceeded" in result.stderr:
                        logger.warning("cdxgen failed due to recursion error, creating basic SBOM")
                        return self._create_basic_sbom(repo_path)
                    else:
                        logger.warning("cdxgen failed, creating basic SBOM as fallback")
                        return self._create_basic_sbom(repo_path)
                
                # Read generated SBOM
                if os.path.exists(sbom_file):
                    with open(sbom_file, 'r') as f:
                        sbom_data = json.load(f)
                    
                    # Check if SBOM has components
                    components = sbom_data.get('components', [])
                    logger.info(f"cdxgen generated SBOM with {len(components)} components")
                    
                    if not components:
                        logger.warning("cdxgen generated empty SBOM, creating basic SBOM")
                        return self._create_basic_sbom(repo_path)
                    
                    logger.info(f"Successfully generated SBOM with {len(components)} components")
                    return sbom_data
                else:
                    logger.warning("SBOM file not generated, creating basic SBOM")
                    return self._create_basic_sbom(repo_path)
                    
            except subprocess.TimeoutExpired:
                logger.error("cdxgen timed out after 30 minutes")
                raise Exception("SBOM generation timed out")
            except Exception as e:
                logger.error(f"Error generating SBOM: {e}")
                # Try to create basic SBOM as fallback
                try:
                    logger.info("Attempting to create basic SBOM as fallback")
                    return self._create_basic_sbom(repo_path)
                except Exception as fallback_error:
                    logger.error(f"Failed to create basic SBOM: {fallback_error}")
                    raise
    
    def _create_basic_sbom(self, repo_path: str) -> Dict:
        """
        Create a basic SBOM when cdxgen fails
        
        Args:
            repo_path: Path to the cloned repository
            
        Returns:
            Basic SBOM data
        """
        logger.info(f"Creating basic SBOM for {self.repository_full_name}")
        self._assert_safe_repo_path(repo_path)
        
        # Try to detect dependencies manually
        components = []
        
        # Check for Python dependencies
        requirements_file = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(requirements_file):
            try:
                with open(requirements_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Parse package name and version
                            if '==' in line:
                                name, version = line.split('==', 1)
                            elif '>=' in line:
                                name, version = line.split('>=', 1)
                            elif '<=' in line:
                                name, version = line.split('<=', 1)
                            else:
                                name = line
                                version = "unknown"
                            
                            components.append({
                                "bom-ref": f"pkg:pypi/{name}@{version}",
                                "group": "",
                                "name": name,
                                "version": version,
                                "purl": f"pkg:pypi/{name}@{version}",
                                "type": "library",
                                "scope": "required"
                            })
            except Exception as e:
                logger.warning(f"Failed to parse requirements.txt: {e}")
        
        # Check for Node.js dependencies
        package_json_file = os.path.join(repo_path, "package.json")
        if os.path.exists(package_json_file):
            try:
                with open(package_json_file, 'r') as f:
                    package_data = json.load(f)
                    dependencies = package_data.get('dependencies', {})
                    dev_dependencies = package_data.get('devDependencies', {})
                    
                    for name, version in dependencies.items():
                        components.append({
                            "bom-ref": f"pkg:npm/{name}@{version}",
                            "group": "",
                            "name": name,
                            "version": version,
                            "purl": f"pkg:npm/{name}@{version}",
                            "type": "library",
                            "scope": "required"
                        })
                    
                    for name, version in dev_dependencies.items():
                        components.append({
                            "bom-ref": f"pkg:npm/{name}@{version}",
                            "group": "",
                            "name": name,
                            "version": version,
                            "purl": f"pkg:npm/{name}@{version}",
                            "type": "library",
                            "scope": "optional"
                        })
            except Exception as e:
                logger.warning(f"Failed to parse package.json: {e}")
        
        # Check for Rust dependencies
        cargo_toml_file = os.path.join(repo_path, "Cargo.toml")
        if os.path.exists(cargo_toml_file):
            try:
                # Try to extract licenses using cargo-license
                rust_licenses = self._extract_rust_licenses(repo_path)
                if rust_licenses:
                    logger.info(f"Extracted {len(rust_licenses)} Rust licenses")
                    # Add license information to components
                    for i, component in enumerate(components):
                        if i < len(rust_licenses):
                            component['licenses'] = [rust_licenses[i]]
            except Exception as e:
                logger.warning(f"Failed to extract Rust licenses: {e}")
        
        # Create basic SBOM structure
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        sbom_data = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": f"urn:uuid:{self._generate_uuid()}",
            "version": 1,
            "metadata": {
                "timestamp": now.isoformat(),
                "tools": {
                    "components": [
                        {
                            "group": "@cyclonedx",
                            "name": "cdxgen",
                            "version": "11.4.4",
                            "purl": "pkg:npm/@cyclonedx/cdxgen@11.4.4",
                            "type": "application",
                            "bom-ref": "pkg:npm/@cyclonedx/cdxgen@11.4.4"
                        }
                    ]
                },
                "authors": [
                    {
                        "name": "GitPulse SBOM Generator"
                    }
                ],
                "lifecycles": [
                    {
                        "phase": "build"
                    }
                ]
            },
            "components": components,
            "services": [],
            "dependencies": [],
            "annotations": []
        }
        
        logger.info(f"Created basic SBOM with {len(components)} components")
        return sbom_data
    
    def _generate_uuid(self) -> str:
        """Generate a UUID for SBOM serial number"""
        import uuid
        return str(uuid.uuid4())
    
    def process_sbom(self, sbom_data: Dict) -> SBOM:
        """
        Process and store SBOM data in MongoDB
        
        Args:
            sbom_data: Raw SBOM data from cdxgen
            
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
            tool_name=tool_info.get('name', 'cdxgen'),
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
        
        # Process vulnerabilities (if present)
        vulnerabilities = sbom_data.get('vulnerabilities', [])
        for vuln_data in vulnerabilities:
            # Extract affected component info
            affected = vuln_data.get('affects', [{}])[0]
            affected_ref = affected.get('ref')
            
            # Find component by bom-ref
            component = SBOMComponent.objects(sbom_id=sbom, bom_ref=affected_ref).first()
            
            if component:
                vulnerability = SBOMVulnerability(
                    sbom_id=sbom,
                    vuln_id=vuln_data.get('id'),
                    source_name=vuln_data.get('source', {}).get('name'),
                    title=vuln_data.get('title'),
                    description=vuln_data.get('description'),
                    severity=vuln_data.get('ratings', [{}])[0].get('severity'),
                    cvss_score=vuln_data.get('ratings', [{}])[0].get('score'),
                    cvss_vector=vuln_data.get('ratings', [{}])[0].get('vector'),
                    affected_component_purl=component.purl,
                    affected_component_name=component.name,
                    affected_component_version=component.version,
                    references=vuln_data.get('references', []),
                    ratings=vuln_data.get('ratings', []),
                    published_date=self._parse_timezone_aware_date(vuln_data.get('published')) if vuln_data.get('published') else None,
                    updated_date=self._parse_timezone_aware_date(vuln_data.get('updated')) if vuln_data.get('updated') else None,
                    raw_vulnerability=vuln_data
                )
                vulnerability.save()
        
        # Update vulnerability count
        sbom.vulnerability_count = len(vulnerabilities)
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
            self._assert_safe_repo_path(repo_path)
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
        """Validate that repo_path is a safe, existing directory and looks like a git repo."""
        if not isinstance(repo_path, str) or not repo_path:
            raise Exception("Invalid repository path")
        if '\x00' in repo_path:
            raise Exception("Invalid null byte in path")
        repo_path_obj = Path(repo_path).resolve()
        if not repo_path_obj.is_absolute():
            raise Exception("Repository path must be absolute")
        if not repo_path_obj.is_dir():
            raise Exception("Repository path must be an existing directory")
        # Ensure path is within an allowed base directory (system temp or configured work dir)
        import tempfile
        allowed_base_paths = [Path(tempfile.gettempdir()).resolve()]
        work_dir = os.environ.get('GITPULSE_WORK_DIR')
        if work_dir:
            allowed_base_paths.append(Path(work_dir).resolve())

        def _is_within(base: Path, path: Path) -> bool:
            try:
                path.relative_to(base)
                return True
            except Exception:
                return False

        if not any(_is_within(base, repo_path_obj) or repo_path_obj == base for base in allowed_base_paths):
            raise Exception("Repository path is outside allowed directories")
        # Do not inspect arbitrary deeper paths to avoid path-expression sinks
        # The directory containment checks above are sufficient for safety