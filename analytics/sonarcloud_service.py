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
    
    def _fetch_historical_metrics(self, project_key: str, repository_full_name: str = None,
                                  from_date: datetime = None, to_date: datetime = None) -> List[Dict]:
        """Fetch historical metrics from SonarCloud API"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return []
            
            url = "https://sonarcloud.io/api/measures/search_history"
            params = {
                'component': project_key,
                'organization': org,
                'metrics': 'bugs,vulnerabilities,code_smells,duplicated_lines_density,coverage,sqale_rating,reliability_rating,security_rating',
                'ps': 100  # Page size
            }
            
            # Add date filters if provided
            if from_date:
                params['from'] = from_date.strftime('%Y-%m-%d')
            if to_date:
                params['to'] = to_date.strftime('%Y-%m-%d')
            
            logger.info(f"Fetching historical metrics for {project_key} with params: {params}")
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                measures = data.get('measures', [])
                logger.info(f"Found {len(measures)} historical measures for {project_key}")
                return measures
            else:
                logger.error(f"Failed to fetch historical metrics: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching historical metrics: {e}")
            return []
    
    def _fetch_historical_issues(self, project_key: str, repository_full_name: str = None,
                                from_date: datetime = None, to_date: datetime = None) -> List[Dict]:
        """Fetch historical issues from SonarCloud API"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return []
            
            url = "https://sonarcloud.io/api/issues/search"
            params = {
                'componentKeys': project_key,
                'organization': org,
                'ps': 100,
                'facets': 'severities,types'
            }
            
            # Add date filters if provided
            if from_date:
                params['createdAfter'] = from_date.strftime('%Y-%m-%d')
            if to_date:
                params['createdBefore'] = to_date.strftime('%Y-%m-%d')
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('issues', [])
            else:
                logger.error(f"Failed to fetch historical issues: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching historical issues: {e}")
            return []
    
    def get_temporal_analysis(self, repository_id: int, repository_full_name: str,
                             from_date: datetime = None, to_date: datetime = None) -> Dict:
        """Get temporal analysis of SonarCloud metrics"""
        try:
            # First, try to get backfilled data from database
            backfilled_data = self._get_backfilled_data(repository_id, from_date, to_date)
            
            if backfilled_data:
                logger.info(f"Using backfilled data for repository {repository_id}")
                return self._process_backfilled_data(backfilled_data, from_date, to_date)
            
            # Fallback to API calls if no backfilled data
            logger.info(f"No backfilled data found, using API for repository {repository_id}")
            project_key = self._get_project_key(repository_full_name)
            
            # Fetch historical data from API
            historical_metrics = self._fetch_historical_metrics(project_key, repository_full_name, from_date, to_date)
            historical_issues = self._fetch_historical_issues(project_key, repository_full_name, from_date, to_date)
            
            # Process historical metrics
            metrics_timeline = []
            for measure in historical_metrics:
                if 'history' in measure:
                    for point in measure['history']:
                        metrics_timeline.append({
                            'date': point.get('date'),
                            'metric': measure.get('metric'),
                            'value': point.get('value')
                        })
            
            # Process historical issues
            issues_timeline = []
            for issue in historical_issues:
                issues_timeline.append({
                    'date': issue.get('creationDate'),
                    'type': issue.get('type'),
                    'severity': issue.get('severity'),
                    'status': issue.get('status'),
                    'resolution': issue.get('resolution')
                })
            
            # Calculate trends
            trends = self._calculate_trends(metrics_timeline, issues_timeline)
            
            return {
                'metrics_timeline': metrics_timeline,
                'issues_timeline': issues_timeline,
                'trends': trends,
                'period': {
                    'from': from_date.isoformat() if from_date else None,
                    'to': to_date.isoformat() if to_date else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting temporal analysis for repository {repository_id}: {e}")
            return {
                'metrics_timeline': [],
                'issues_timeline': [],
                'trends': {},
                'error': str(e)
            }
    
    def _get_backfilled_data(self, repository_id: int, from_date: datetime = None, to_date: datetime = None) -> List[SonarCloudMetrics]:
        """Get backfilled data from database"""
        try:
            query = SonarCloudMetrics.objects.filter(repository_id=repository_id)
            
            if from_date:
                query = query.filter(last_analysis_date__gte=from_date)
            if to_date:
                query = query.filter(last_analysis_date__lte=to_date)
            
            return list(query.order_by('last_analysis_date'))
            
        except Exception as e:
            logger.error(f"Error getting backfilled data: {e}")
            return []
    
    def _process_backfilled_data(self, backfilled_data: List[SonarCloudMetrics], 
                                from_date: datetime = None, to_date: datetime = None) -> Dict:
        """Process backfilled data into timeline format"""
        try:
            # Convert to timeline format
            metrics_timeline = []
            
            for metrics in backfilled_data:
                # Add maintainability rating
                if metrics.maintainability_rating:
                    metrics_timeline.append({
                        'date': metrics.last_analysis_date.isoformat(),
                        'metric': 'maintainability_rating',
                        'value': metrics.maintainability_rating
                    })
                
                # Add reliability rating
                if metrics.reliability_rating:
                    metrics_timeline.append({
                        'date': metrics.last_analysis_date.isoformat(),
                        'metric': 'reliability_rating',
                        'value': metrics.reliability_rating
                    })
                
                # Add security rating
                if metrics.security_rating:
                    metrics_timeline.append({
                        'date': metrics.last_analysis_date.isoformat(),
                        'metric': 'security_rating',
                        'value': metrics.security_rating
                    })
                
                # Add bugs count
                metrics_timeline.append({
                    'date': metrics.last_analysis_date.isoformat(),
                    'metric': 'bugs',
                    'value': metrics.bugs
                })
                
                # Add vulnerabilities count
                metrics_timeline.append({
                    'date': metrics.last_analysis_date.isoformat(),
                    'metric': 'vulnerabilities',
                    'value': metrics.vulnerabilities
                })
                
                # Add code smells count
                metrics_timeline.append({
                    'date': metrics.last_analysis_date.isoformat(),
                    'metric': 'code_smells',
                    'value': metrics.code_smells
                })
                
                # Add coverage
                if metrics.coverage is not None:
                    metrics_timeline.append({
                        'date': metrics.last_analysis_date.isoformat(),
                        'metric': 'coverage',
                        'value': metrics.coverage
                    })
            
            # Calculate trends from backfilled data
            trends = self._calculate_trends(metrics_timeline, [])
            
            return {
                'metrics_timeline': metrics_timeline,
                'issues_timeline': [],  # We don't have historical issues data
                'trends': trends,
                'period': {
                    'from': from_date.isoformat() if from_date else None,
                    'to': to_date.isoformat() if to_date else None
                },
                'data_source': 'backfilled'
            }
            
            return {
                'metrics_timeline': metrics_timeline,
                'issues_timeline': [],  # We don't have historical issues data
                'trends': trends,
                'period': {
                    'from': from_date.isoformat() if from_date else None,
                    'to': to_date.isoformat() if to_date else None
                },
                'data_source': 'backfilled'
            }
            
        except Exception as e:
            logger.error(f"Error processing backfilled data: {e}")
            return {
                'metrics_timeline': [],
                'issues_timeline': [],
                'trends': {},
                'error': str(e)
            }
    
    def _calculate_trends(self, metrics_timeline: List[Dict], issues_timeline: List[Dict]) -> Dict:
        """Calculate trends from timeline data"""
        trends = {
            'quality_gate_trend': 'stable',
            'maintainability_trend': 'stable',
            'reliability_trend': 'stable',
            'security_trend': 'stable',
            'issues_trend': 'stable',
            'coverage_trend': 'stable'
        }
        
        # Simple trend calculation (can be enhanced)
        if metrics_timeline:
            # Group by metric and calculate trend
            metrics_by_type = {}
            for point in metrics_timeline:
                metric = point['metric']
                if metric not in metrics_by_type:
                    metrics_by_type[metric] = []
                metrics_by_type[metric].append(point)
            
            # Calculate trends for each metric type
            for metric, points in metrics_by_type.items():
                if len(points) >= 2:
                    # Sort by date
                    sorted_points = sorted(points, key=lambda x: x['date'])
                    first_value = sorted_points[0]['value']
                    last_value = sorted_points[-1]['value']
                    
                    # Handle different metric types
                    if metric in ['maintainability_rating', 'reliability_rating', 'security_rating']:
                        # For ratings (A=1, B=2, C=3, D=4, E=5)
                        rating_to_num = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5}
                        first_num = rating_to_num.get(first_value, 3)
                        last_num = rating_to_num.get(last_value, 3)
                        
                        if last_num < first_num:  # Lower number = better rating
                            trends[f'{metric}_trend'] = 'improving'
                        elif last_num > first_num:
                            trends[f'{metric}_trend'] = 'degrading'
                        else:
                            trends[f'{metric}_trend'] = 'stable'
                    else:
                        # For numeric metrics
                        try:
                            first_num = float(first_value) if first_value else 0
                            last_num = float(last_value) if last_value else 0
                            
                            # Determine trend
                            if last_num > first_num * 1.1:  # 10% improvement
                                trends[f'{metric}_trend'] = 'improving'
                            elif last_num < first_num * 0.9:  # 10% degradation
                                trends[f'{metric}_trend'] = 'degrading'
                            else:
                                trends[f'{metric}_trend'] = 'stable'
                        except (ValueError, TypeError):
                            trends[f'{metric}_trend'] = 'stable'
        
        return trends 

    def _fetch_project_analyses(self, project_key: str, repository_full_name: str = None, 
                               from_date: datetime = None, to_date: datetime = None) -> List[Dict]:
        """Fetch historical project analyses from SonarCloud API"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return []
            
            url = "https://sonarcloud.io/api/project_analyses/search"
            params = {
                'project': project_key,
                'organization': org,
                'ps': 100  # Page size
            }
            
            # Add date filters if provided
            if from_date:
                params['from'] = from_date.strftime('%Y-%m-%d')
            if to_date:
                params['to'] = to_date.strftime('%Y-%m-%d')
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('analyses', [])
            else:
                logger.error(f"Failed to fetch project analyses: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching project analyses: {e}")
            return []
    
    def backfill_historical_data(self, repository_id: int, repository_full_name: str,
                               from_date: datetime = None, to_date: datetime = None) -> Dict:
        """Backfill historical SonarCloud data for a repository"""
        try:
            logger.info(f"Starting backfill for repository {repository_full_name}")
            
            project_key = self._get_project_key(repository_full_name)
            
            # Fetch historical analyses
            analyses = self._fetch_project_analyses(project_key, repository_full_name, from_date, to_date)
            
            # Fetch historical metrics for each analysis
            backfilled_data = []
            
            for analysis in analyses:
                analysis_key = analysis.get('key')
                analysis_date = analysis.get('date')
                
                if analysis_key and analysis_date:
                    # Fetch metrics for this specific analysis
                    metrics = self._fetch_metrics_for_analysis(project_key, analysis_key, repository_full_name)
                    
                    if metrics:
                        backfilled_data.append({
                            'analysis_key': analysis_key,
                            'date': analysis_date,
                            'metrics': metrics
                        })
            
            # Store backfilled data in database
            stored_count = self._store_backfilled_data(repository_id, backfilled_data, repository_full_name)
            
            return {
                'success': True,
                'analyses_found': len(analyses),
                'data_points_stored': stored_count,
                'period': {
                    'from': from_date.isoformat() if from_date else None,
                    'to': to_date.isoformat() if to_date else None
                }
            }
            
        except Exception as e:
            logger.error(f"Error backfilling data for repository {repository_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _fetch_metrics_for_analysis(self, project_key: str, analysis_key: str, 
                                   repository_full_name: str = None) -> Optional[Dict]:
        """Fetch metrics for a specific analysis"""
        try:
            org = self._get_organization(repository_full_name)
            if not org:
                return None
            
            url = "https://sonarcloud.io/api/measures/component"
            params = {
                'component': project_key,
                'organization': org,
                'analysis': analysis_key,
                'metricKeys': 'bugs,vulnerabilities,code_smells,duplicated_lines_density,coverage,sqale_rating,reliability_rating,security_rating,maintainability_rating'
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('component', {}).get('measures', [])
            else:
                logger.warning(f"Failed to fetch metrics for analysis {analysis_key}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching metrics for analysis {analysis_key}: {e}")
            return None
    
    def _store_backfilled_data(self, repository_id: int, backfilled_data: List[Dict], repository_full_name: str) -> int:
        """Store backfilled data in the database"""
        stored_count = 0
        
        for data_point in backfilled_data:
            try:
                # Parse the analysis date
                analysis_date = datetime.fromisoformat(data_point['date'].replace('Z', '+00:00'))
                
                # Extract metrics
                metrics = data_point['metrics']
                metrics_dict = {m.get('metric'): m.get('value') for m in metrics}
                
                # Get project key
                project_key = self._get_project_key(repository_full_name)
                
                # Create SonarCloudMetrics document
                metrics_doc = SonarCloudMetrics(
                    repository_id=repository_id,
                    repository_full_name=repository_full_name,
                    sonarcloud_project_key=project_key,
                    sonarcloud_organization=self._get_organization(repository_full_name),
                    last_analysis_date=analysis_date,
                    
                    # Ratings
                    maintainability_rating=self._convert_rating_to_letter(metrics_dict.get('sqale_rating')),
                    reliability_rating=self._convert_rating_to_letter(metrics_dict.get('reliability_rating')),
                    security_rating=self._convert_rating_to_letter(metrics_dict.get('security_rating')),
                    
                    # Quantitative metrics
                    bugs=int(metrics_dict.get('bugs', 0)),
                    vulnerabilities=int(metrics_dict.get('vulnerabilities', 0)),
                    code_smells=int(metrics_dict.get('code_smells', 0)),
                    duplicated_lines_density=float(metrics_dict.get('duplicated_lines_density', 0.0)),
                    coverage=float(metrics_dict.get('coverage', 0.0)) if metrics_dict.get('coverage') else None,
                    technical_debt=float(metrics_dict.get('technical_debt', 0.0)) if metrics_dict.get('technical_debt') else None,
                    
                    # Quality gate (we don't have historical quality gate data)
                    quality_gate='UNKNOWN'
                )
                
                metrics_doc.save()
                stored_count += 1
                
            except Exception as e:
                logger.error(f"Error storing backfilled data point: {e}")
                continue
        
        return stored_count 