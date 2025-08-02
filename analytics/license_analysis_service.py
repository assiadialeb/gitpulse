"""
License analysis service for SBOM components
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from .models import SBOM, SBOMComponent

logger = logging.getLogger(__name__)


class LicenseAnalysisService:
    """Service for analyzing license compatibility from SBOM data"""
    
    # License categories
    COMMERCIAL_FRIENDLY = {
        'MIT', 'MIT-0', 'MIT-1.0', 'MIT-2.0',
        'APACHE', 'APACHE-2.0', 'APACHE-1.1', 'APACHE-1.0',
        'BSD', 'BSD-2-CLAUSE', 'BSD-3-CLAUSE', 'BSD-4-CLAUSE',
        'ISC', 'UNLICENSE', 'CC0', 'CC0-1.0',
        'WTFPL', 'ZERO-CLAUSE-BSD', '0BSD'
    }
    
    COPYLEFT_STRICT = {
        'GPL', 'GPL-1.0', 'GPL-2.0', 'GPL-3.0',
        'AGPL', 'AGPL-1.0', 'AGPL-3.0',
        'CC-BY-SA', 'CC-BY-SA-1.0', 'CC-BY-SA-2.0', 'CC-BY-SA-3.0', 'CC-BY-SA-4.0'
    }
    
    COPYLEFT_MODERATE = {
        'LGPL', 'LGPL-2.0', 'LGPL-2.1', 'LGPL-3.0',
        'MPL', 'MPL-1.0', 'MPL-2.0',
        'EPL', 'EPL-1.0', 'EPL-2.0'
    }
    
    def __init__(self, repository_full_name: str):
        self.repository_full_name = repository_full_name
    
    def get_latest_sbom(self) -> Optional[SBOM]:
        """Get the latest SBOM for the repository"""
        return SBOM.objects(repository_full_name=self.repository_full_name).order_by('-generated_at').first()
    
    def analyze_commercial_compatibility(self) -> Dict:
        """
        Analyze commercial compatibility of SBOM components
        
        Returns:
            Dictionary with analysis results
        """
        sbom = self.get_latest_sbom()
        if not sbom:
            return {
                'has_sbom': False,
                'message': 'No SBOM found for this repository'
            }
        
        components = SBOMComponent.objects(sbom_id=sbom)
        
        analysis = {
            'has_sbom': True,
            'sbom_generated_at': sbom.generated_at,
            'total_components': components.count(),
            'compatible': True,
            'warnings': [],
            'incompatible_components': [],
            'license_summary': {},
            'component_details': []
        }
        
        for component in components:
            licenses = component.licenses or []
            component_info = {
                'name': component.name,
                'version': component.version,
                'group': component.group,
                'purl': component.purl,
                'licenses': [],
                'commercial_compatible': True,
                'warnings': []
            }
            
            for license_data in licenses:
                # Handle different license formats
                if 'license' in license_data:
                    license_info = license_data.get('license', {})
                    license_id = license_info.get('id', '').upper()
                    license_name = license_info.get('name', license_id if license_id else 'Unknown')
                elif 'expression' in license_data:
                    license_id = license_data.get('expression', '').upper()
                    license_name = license_id
                else:
                    license_id = 'UNKNOWN'
                    license_name = 'Unknown'
                
                component_info['licenses'].append({
                    'id': license_id,
                    'name': license_name
                })
                
                # Count licenses
                if license_id not in analysis['license_summary']:
                    analysis['license_summary'][license_id] = 0
                analysis['license_summary'][license_id] += 1
                
                # Check compatibility
                if license_id in self.COPYLEFT_STRICT:
                    component_info['commercial_compatible'] = False
                    component_info['warnings'].append(f'Copyleft license: {license_id}')
                    analysis['warnings'].append({
                        'component': f"{component.name}@{component.version}",
                        'license': license_id,
                        'issue': 'Copyleft license - source code must be shared'
                    })
                    analysis['incompatible_components'].append({
                        'name': component.name,
                        'version': component.version,
                        'license': license_id,
                        'issue': 'Copyleft license'
                    })
                    analysis['compatible'] = False
                    
                elif license_id in self.COPYLEFT_MODERATE:
                    component_info['warnings'].append(f'LGPL/MPL license: {license_id}')
                    analysis['warnings'].append({
                        'component': f"{component.name}@{component.version}",
                        'license': license_id,
                        'issue': 'LGPL/MPL - modifications may need to be shared'
                    })
            
            analysis['component_details'].append(component_info)
        
        # Generate recommendations
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _generate_recommendations(self, analysis: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        if not analysis['compatible']:
            recommendations.append("⚠️ Some components have copyleft licenses that require source code sharing")
        
        if analysis['warnings']:
            recommendations.append("📋 Review components with LGPL/MPL licenses for modification requirements")
        
        commercial_friendly_count = sum(
            count for license_id, count in analysis['license_summary'].items()
            if license_id in self.COMMERCIAL_FRIENDLY
        )
        
        if commercial_friendly_count > 0:
            recommendations.append(f"✅ {commercial_friendly_count} components have commercial-friendly licenses")
        
        if not analysis['component_details']:
            recommendations.append("📦 No components found in SBOM")
        
        return recommendations 