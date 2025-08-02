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
        
        # Prepare environment variables
        env = os.environ.copy()
        if self.oss_config.email:
            env['OSSINDEX_USERNAME'] = self.oss_config.email
        if self.oss_config.api_token:
            env['OSSINDEX_TOKEN'] = self.oss_config.api_token
        
        # Create temporary directory for SBOM output
        with tempfile.TemporaryDirectory() as temp_dir:
            sbom_file = os.path.join(temp_dir, "sbom.json")
            
            # Build cdxgen command
            cmd = [
                'npx', '@cyclonedx/cdxgen',
                '--include-vulnerabilities',
                '-o', sbom_file,
                repo_path
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
                    cwd=temp_dir
                )
                
                if result.returncode != 0:
                    logger.error(f"cdxgen failed: {result.stderr}")
                    raise Exception(f"cdxgen failed: {result.stderr}")
                
                # Read generated SBOM
                if os.path.exists(sbom_file):
                    with open(sbom_file, 'r') as f:
                        sbom_data = json.load(f)
                    
                    logger.info(f"Successfully generated SBOM with {len(sbom_data.get('components', []))} components")
                    return sbom_data
                else:
                    raise Exception("SBOM file not generated")
                    
            except subprocess.TimeoutExpired:
                logger.error("cdxgen timed out after 30 minutes")
                raise Exception("SBOM generation timed out")
            except Exception as e:
                logger.error(f"Error generating SBOM: {e}")
                raise
    
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
        sbom = SBOM(
            repository_full_name=self.repository_full_name,
            bom_format=sbom_data.get('bomFormat'),
            spec_version=sbom_data.get('specVersion'),
            serial_number=sbom_data.get('serialNumber'),
            version=sbom_data.get('version'),
            generated_at=datetime.fromisoformat(metadata.get('timestamp', '').replace('Z', '+00:00')),
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
                    published_date=datetime.fromisoformat(vuln_data.get('published', '').replace('Z', '+00:00')) if vuln_data.get('published') else None,
                    updated_date=datetime.fromisoformat(vuln_data.get('updated', '').replace('Z', '+00:00')) if vuln_data.get('updated') else None,
                    raw_vulnerability=vuln_data
                )
                vulnerability.save()
        
        # Update vulnerability count
        sbom.vulnerability_count = len(vulnerabilities)
        sbom.save()
        
        logger.info(f"Processed SBOM with {sbom.component_count} components and {sbom.vulnerability_count} vulnerabilities")
        return sbom 