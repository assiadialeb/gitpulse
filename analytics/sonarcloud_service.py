"""
SonarCloud service for fetching and processing quality metrics
"""
import logging
import requests
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Optional, List
from django.utils import timezone

from .models import SonarCloudMetrics
from sonarcloud.models import SonarCloudConfig

logger = logging.getLogger(__name__)


class SonarCloudService:
    """Service for interacting with SonarCloud API"""
    
    def __init__(self):
        self.config = SonarCloudConfig.get_config()
        self.headers = {
            'Authorization': f'Bearer {self.config.access_token}',
            'Content-Type': 'application/json'
        }
        self.organization = None
    
    def _detect_organization(self) -> Optional[str]:
        """Detect the SonarCloud organization"""
        try:
            # Try to get user info first
            user_url = "https://sonarcloud.io/api/users/current"
            user_response = requests.get(user_url, headers=self.headers, timeout=10)
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                # Use external identity as organization
                organization = user_data.get('externalIdentity')
                if organization:
                    logger.info(f"Detected SonarCloud organization: {organization}")
                    return organization
            
            logger.error("Could not detect SonarCloud organization")
            return None
            
        except Exception as e:
            logger.error(f"Error detecting organization: {e}")
            return None
    
    def _get_organization(self, repository_full_name: str = None) -> str:
        """Get or detect the organization"""
        if repository_full_name:
            # Extract organization from repository name
            return repository_full_name.split('/')[0]
        else:
            # Fallback to user's organization
            if not self.organization:
                self.organization = self._detect_organization()
            return self.organization
    
    def _get_project_key(self, repository_full_name: str) -> str:
        """Generate SonarCloud project key from repository name"""
        # Only replace / with _, keep - as is
        return repository_full_name.replace("/", "_")
    
    def _convert_rating_to_letter(self, rating_value) -> Optional[str]:
        """Convert numeric rating to letter grade (A=1, B=2, C=3, D=4, E=5)"""
        if rating_value is None:
            return None
        
        try:
            rating_num = float(rating_value)
            if rating_num == 1.0:
                return 'A'
            elif rating_num == 2.0:
                return 'B'
            elif rating_num == 3.0:
                return 'C'
            elif rating_num == 4.0:
                return 'D'
            elif rating_num == 5.0:
                return 'E'
            else:
                return None
        except (ValueError, TypeError):
            return None
    
    def _fetch_quality_gate(self, project_key: str, repository_full_name: str = None) -> Optional[str]:
        """Fetch quality gate status for a project"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return None
            
            url = "https://sonarcloud.io/api/qualitygates/project_status"
            params = {
                'organization': org,
                'projectKey': project_key
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                project_status = data.get('projectStatus', {})
                status = project_status.get('status', 'FAIL')
                return status.upper()
            
            logger.warning(f"Could not fetch quality gate for {project_key}: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching quality gate for {project_key}: {e}")
            return None
    
    def _fetch_metrics(self, project_key: str, repository_full_name: str = None) -> Dict:
        """Fetch quality metrics for a project"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return {}
            
            url = "https://sonarcloud.io/api/measures/component"
            params = {
                'organization': org,
                'component': project_key,
                'metricKeys': 'bugs,vulnerabilities,code_smells,coverage,duplicated_lines_density,technical_debt,sqale_rating,reliability_rating,security_rating'
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                component = data.get('component', {})
                measures = component.get('measures', [])
                
                metrics = {}
                for measure in measures:
                    metric_key = measure.get('metric')
                    value = measure.get('value', '0')
                    metrics[metric_key] = value
                
                return metrics
            
            logger.warning(f"Could not fetch metrics for {project_key}: {response.status_code}")
            logger.warning(f"Response: {response.text}")
            return {}
            
        except Exception as e:
            logger.error(f"Error fetching metrics for {project_key}: {e}")
            return {}
    
    def _fetch_issues(self, project_key: str, repository_full_name: str = None) -> Dict:
        """Fetch issues summary for a project"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return {}
            
            url = "https://sonarcloud.io/api/issues/search"
            params = {
                'organization': org,
                'componentKeys': project_key,
                'resolved': 'false',
                'facets': 'severities'
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                total_issues = data.get('total', 0)
                
                # Parse severity breakdown
                issues_by_severity = {
                    'BLOCKER': 0,
                    'CRITICAL': 0,
                    'MAJOR': 0,
                    'MINOR': 0,
                    'INFO': 0
                }
                
                facets = data.get('facets', [])
                for facet in facets:
                    if facet.get('property') == 'severities':
                        for value in facet.get('values', []):
                            severity = value.get('val')
                            count = value.get('count', 0)
                            if severity in issues_by_severity:
                                issues_by_severity[severity] = count
                
                return {
                    'total': total_issues,
                    'by_severity': issues_by_severity
                }
            
            logger.warning(f"Could not fetch issues for {project_key}: {response.status_code}")
            return {}
            
        except Exception as e:
            logger.error(f"Error fetching issues for {project_key}: {e}")
            return {}
    
    def _fetch_project_info(self, project_key: str, repository_full_name: str = None) -> Dict:
        """Fetch basic project information"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return {}
            
            url = "https://sonarcloud.io/api/projects/search"
            params = {
                'organization': org,
                'projects': project_key
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                projects = data.get('components', [])
                
                if projects:
                    project = projects[0]
                    return {
                        'key': project.get('key'),
                        'name': project.get('name'),
                        'last_analysis_date': project.get('lastAnalysisDate')
                    }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error fetching project info for {project_key}: {e}")
            return {}
    
    def index_metrics_for_repository(self, repository_id: int, repository_full_name: str) -> Dict:
        """Index SonarCloud metrics for a repository"""
        try:
            logger.info(f"Starting SonarCloud indexing for repository {repository_full_name}")
            
            # Generate project key
            project_key = self._get_project_key(repository_full_name)
            
            # Check if project exists
            project_info = self._fetch_project_info(project_key, repository_full_name)
            if not project_info:
                logger.warning(f"Project {project_key} not found in SonarCloud")
                return {
                    'success': False,
                    'error': f'Project {project_key} not found in SonarCloud'
                }
            
            # Fetch all data
            quality_gate = self._fetch_quality_gate(project_key, repository_full_name)
            metrics = self._fetch_metrics(project_key, repository_full_name)
            issues = self._fetch_issues(project_key, repository_full_name)
            
            # Parse last analysis date
            last_analysis_date = None
            if project_info.get('last_analysis_date'):
                try:
                    last_analysis_date = datetime.fromisoformat(
                        project_info['last_analysis_date'].replace('Z', '+00:00')
                    )
                except:
                    pass
            
            # Create metrics document
            metrics_doc = SonarCloudMetrics(
                repository_id=repository_id,
                repository_full_name=repository_full_name,
                sonarcloud_project_key=project_key,
                sonarcloud_organization=self._get_organization(repository_full_name),
                quality_gate=quality_gate if quality_gate in ['PASS', 'FAIL'] else 'FAIL',
                last_analysis_date=last_analysis_date,
                
                # Ratings - convert numeric ratings to letter grades
                maintainability_rating=self._convert_rating_to_letter(metrics.get('sqale_rating')),
                reliability_rating=self._convert_rating_to_letter(metrics.get('reliability_rating')),
                security_rating=self._convert_rating_to_letter(metrics.get('security_rating')),
                
                # Quantitative metrics
                bugs=int(metrics.get('bugs', 0)),
                vulnerabilities=int(metrics.get('vulnerabilities', 0)),
                code_smells=int(metrics.get('code_smells', 0)),
                duplicated_lines_density=float(metrics.get('duplicated_lines_density', 0.0)),
                coverage=float(metrics.get('coverage', 0.0)) if metrics.get('coverage') else None,
                technical_debt=float(metrics.get('technical_debt', 0.0)) if metrics.get('technical_debt') else None,
                
                # Issues by severity
                issues_blocker=issues.get('by_severity', {}).get('BLOCKER', 0),
                issues_critical=issues.get('by_severity', {}).get('CRITICAL', 0),
                issues_major=issues.get('by_severity', {}).get('MAJOR', 0),
                issues_minor=issues.get('by_severity', {}).get('MINOR', 0),
                issues_info=issues.get('by_severity', {}).get('INFO', 0),
            )
            
            metrics_doc.save()
            
            logger.info(f"Successfully indexed SonarCloud metrics for {repository_full_name}")
            
            return {
                'success': True,
                'project_key': project_key,
                'quality_gate': quality_gate,
                'total_issues': metrics_doc.total_issues(),
                'metrics_id': str(metrics_doc.id)
            }
            
        except Exception as e:
            logger.error(f"Error indexing SonarCloud metrics for {repository_full_name}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_latest_metrics(self, repository_id: int) -> Optional[SonarCloudMetrics]:
        """Get the latest SonarCloud metrics for a repository"""
        try:
            return SonarCloudMetrics.objects.filter(
                repository_id=repository_id
            ).order_by('-timestamp').first()
        except Exception as e:
            logger.error(f"Error getting latest metrics for repository {repository_id}: {e}")
            return None 