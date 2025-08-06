"""
CodeQL Security Analysis Service for GitHub repositories
"""
import logging
import requests
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import Dict, List, Optional, Tuple
from django.conf import settings

from .github_token_service import GitHubTokenService
from .models import CodeQLVulnerability

logger = logging.getLogger(__name__)


class CodeQLService:
    """Service for fetching and processing CodeQL security analysis data from GitHub"""
    
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize CodeQL service
        
        Args:
            github_token: Optional GitHub token, if not provided will use token service
        """
        self.github_token = github_token
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        
        if self.github_token:
            self.session.headers.update({
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'GitPulse-Analytics/1.0'
            })
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Tuple[Optional[Dict], bool]:
        """
        Make a request to GitHub API with error handling
        
        Args:
            url: API endpoint URL
            params: Optional query parameters
            
        Returns:
            Tuple of (response_data, success)
        """
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 404:
                logger.info(f"CodeQL analysis not available for {url} - likely not enabled on repository")
                return None, False
            elif response.status_code == 403:
                # Check if it's specifically about code scanning not being enabled
                error_msg = response.text
                if 'code scanning not enabled' in error_msg.lower() or 'advanced security' in error_msg.lower():
                    logger.info(f"CodeQL/Advanced Security not enabled for {url}")
                    return None, False
                else:
                    logger.error(f"Access forbidden for {url} - check permissions: {error_msg}")
                    return None, False
            elif response.status_code == 401:
                logger.error(f"Unauthorized access to {url} - check token permissions")
                return None, False
            elif response.status_code == 422:
                logger.info(f"CodeQL analysis not available for {url} - repository may not support code scanning")
                return None, False
            elif response.status_code != 200:
                logger.error(f"GitHub API error {response.status_code} for {url}: {response.text}")
                return None, False
            
            return response.json(), True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None, False
    
    def fetch_codeql_alerts(self, repo_full_name: str, state: str = "open", 
                           per_page: int = 100, page: int = 1) -> Tuple[List[Dict], bool]:
        """
        Fetch CodeQL security alerts for a repository
        
        Args:
            repo_full_name: Repository full name (owner/repo)
            state: Alert state ('open', 'dismissed', 'fixed', or 'all')
            per_page: Number of alerts per page
            page: Page number
            
        Returns:
            Tuple of (alerts_list, success)
        """
        url = f"{self.base_url}/repos/{repo_full_name}/code-scanning/alerts"
        params = {
            'state': state,
            'per_page': per_page,
            'page': page,
            'sort': 'created',
            'direction': 'desc'
        }
        
        logger.info(f"Fetching CodeQL alerts for {repo_full_name} (state: {state}, page: {page})")
        
        data, success = self._make_request(url, params)
        if not success or data is None:
            return [], False
        
        # Handle both single alert and list of alerts
        if isinstance(data, dict):
            return [data], True
        elif isinstance(data, list):
            return data, True
        else:
            logger.error(f"Unexpected response format for {repo_full_name}: {type(data)}")
            return [], False
    
    def fetch_all_codeql_alerts(self, repo_full_name: str, 
                               states: List[str] = None) -> Tuple[List[Dict], bool]:
        """
        Fetch all CodeQL alerts for a repository across all states
        
        Args:
            repo_full_name: Repository full name (owner/repo)
            states: List of states to fetch (default: ['open', 'dismissed', 'fixed'])
            
        Returns:
            Tuple of (all_alerts, success)
        """
        if states is None:
            states = ['open', 'dismissed', 'fixed']
        
        all_alerts = []
        
        for state in states:
            page = 1
            while True:
                alerts, success = self.fetch_codeql_alerts(
                    repo_full_name, state=state, page=page
                )
                
                if not success:
                    logger.error(f"Failed to fetch alerts for {repo_full_name} state {state}")
                    return all_alerts, False
                
                if not alerts:  # No more alerts
                    break
                
                all_alerts.extend(alerts)
                
                # GitHub API pagination - if we got less than per_page, we're done
                if len(alerts) < 100:
                    break
                
                page += 1
                
                # Safety limit to avoid infinite loops
                if page > 50:
                    logger.warning(f"Reached page limit for {repo_full_name} state {state}")
                    break
        
        logger.info(f"Fetched {len(all_alerts)} total CodeQL alerts for {repo_full_name}")
        return all_alerts, True
    
    def process_codeql_alert(self, alert_data: Dict, repo_full_name: str) -> Optional[CodeQLVulnerability]:
        """
        Process a single CodeQL alert and convert to our model
        
        Args:
            alert_data: Raw alert data from GitHub API
            repo_full_name: Repository full name
            
        Returns:
            CodeQLVulnerability instance or None if processing fails
        """
        try:
            # Extract basic information
            alert_number = alert_data.get('number')
            rule_info = alert_data.get('rule', {})
            most_recent_instance = alert_data.get('most_recent_instance', {})
            
            # Parse dates
            created_at = None
            if alert_data.get('created_at'):
                created_at = datetime.fromisoformat(
                    alert_data['created_at'].replace('Z', '+00:00')
                )
            
            updated_at = None
            if alert_data.get('updated_at'):
                updated_at = datetime.fromisoformat(
                    alert_data['updated_at'].replace('Z', '+00:00')
                )
            
            dismissed_at = None
            if alert_data.get('dismissed_at'):
                dismissed_at = datetime.fromisoformat(
                    alert_data['dismissed_at'].replace('Z', '+00:00')
                )
            
            fixed_at = None
            if alert_data.get('fixed_at'):
                fixed_at = datetime.fromisoformat(
                    alert_data['fixed_at'].replace('Z', '+00:00')
                )
            
            # Extract location information
            location = most_recent_instance.get('location', {})
            
            # Debug: Log the actual severity value from GitHub
            raw_severity = rule_info.get('severity', 'medium')
            logger.info(f"Raw severity from GitHub: '{raw_severity}' for alert {alert_data.get('id')}")
            
            # Map GitHub severity values to our model values
            severity_mapping = {
                'error': 'critical',
                'warning': 'high', 
                'note': 'medium',
                'critical': 'critical',
                'high': 'high',
                'medium': 'medium',
                'low': 'low'
            }
            mapped_severity = severity_mapping.get(raw_severity.lower(), 'medium')
            
            # Create vulnerability instance
            vulnerability = CodeQLVulnerability(
                repository_full_name=repo_full_name,
                vulnerability_id=str(alert_data.get('id', alert_number)),
                rule_id=rule_info.get('id', 'unknown'),
                rule_description=rule_info.get('description', ''),
                rule_name=rule_info.get('name', ''),
                severity=mapped_severity,
                confidence=rule_info.get('precision', 'medium').lower(),
                state=alert_data.get('state', 'open').lower(),
                dismissed_reason=alert_data.get('dismissed_reason'),
                dismissed_comment=alert_data.get('dismissed_comment'),
                file_path=location.get('path'),
                start_line=location.get('start_line'),
                end_line=location.get('end_line'),
                start_column=location.get('start_column'),
                end_column=location.get('end_column'),
                message=most_recent_instance.get('message', {}).get('text', ''),
                description=rule_info.get('full_description', ''),
                category=self._extract_category(rule_info),
                cwe_id=self._extract_cwe_id(rule_info),
                created_at=created_at or datetime.now(dt_timezone.utc),
                updated_at=updated_at or datetime.now(dt_timezone.utc),
                dismissed_at=dismissed_at,
                fixed_at=fixed_at,
                html_url=alert_data.get('html_url'),
                number=alert_number,
                tool_name='CodeQL',
                tool_version=most_recent_instance.get('analysis_key'),
                payload=alert_data
            )
            
            return vulnerability
            
        except Exception as e:
            logger.error(f"Failed to process CodeQL alert {alert_data.get('id')}: {e}")
            return None
    
    def _extract_category(self, rule_info: Dict) -> str:
        """Extract security category from rule information"""
        rule_id = rule_info.get('id', '').lower()
        tags = rule_info.get('tags', [])
        
        # Map common CodeQL rules to categories
        if 'sql-injection' in rule_id or 'sql' in tags:
            return 'sql-injection'
        elif 'xss' in rule_id or 'cross-site-scripting' in tags:
            return 'xss'
        elif 'path-traversal' in rule_id or 'path' in tags:
            return 'path-traversal'
        elif 'command-injection' in rule_id or 'command' in tags:
            return 'command-injection'
        elif 'authentication' in rule_id or 'auth' in tags:
            return 'authentication'
        elif 'authorization' in rule_id or 'authz' in tags:
            return 'authorization'
        elif 'crypto' in rule_id or 'cryptography' in tags:
            return 'cryptography'
        elif 'information-exposure' in rule_id:
            return 'information-disclosure'
        else:
            return 'other'
    
    def _extract_cwe_id(self, rule_info: Dict) -> Optional[str]:
        """Extract CWE ID from rule information"""
        tags = rule_info.get('tags', [])
        for tag in tags:
            if tag.startswith('CWE-'):
                return tag
        return None
    
    def calculate_security_level(self, vulnerabilities: List[CodeQLVulnerability]) -> Dict:
        """
        Calculate security level based on the most critical open vulnerability
        
        Args:
            vulnerabilities: List of vulnerabilities for a repository
            
        Returns:
            Dictionary with security metrics and level
        """
        if not vulnerabilities:
            return {
                'level': 'safe',
                'level_display': 'Safe',
                'total_vulnerabilities': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0,
                'low_count': 0,
                'open_count': 0,
                'fixed_count': 0,
                'dismissed_count': 0,
                'categories': {},
                'trend': 'stable'
            }
        
        # Count by severity (only open vulnerabilities)
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        state_counts = {'open': 0, 'fixed': 0, 'dismissed': 0}
        categories = {}
        
        for vuln in vulnerabilities:
            state_counts[vuln.state] += 1
            
            # Only count severity for OPEN vulnerabilities
            if vuln.state == 'open':
                severity_counts[vuln.severity] += 1
            
            category = vuln.category or 'other'
            categories[category] = categories.get(category, 0) + 1
        
        # Determine security level based on most critical open vulnerability
        open_vulnerabilities = [v for v in vulnerabilities if v.state == 'open']
        
        if not open_vulnerabilities:
            level = 'safe'
            level_display = 'Safe'
        else:
            # Find the most critical open vulnerability
            severity_order = ['critical', 'high', 'medium', 'low']
            max_severity = None
            
            for severity in severity_order:
                if any(v.severity == severity for v in open_vulnerabilities):
                    max_severity = severity
                    break
            
            if max_severity == 'critical':
                level = 'critical'
                level_display = 'Critical'
            elif max_severity == 'high':
                level = 'high'
                level_display = 'High'
            elif max_severity == 'medium':
                level = 'medium'
                level_display = 'Medium'
            elif max_severity == 'low':
                level = 'low'
                level_display = 'Low'
            else:
                level = 'safe'
                level_display = 'Safe'
        
        # Calculate trend (simplified - based on recent activity)
        recent_vulns = [v for v in vulnerabilities if v.get_age_days() <= 30]
        if len(recent_vulns) > len(vulnerabilities) * 0.3:
            trend = 'degrading'
        elif any(v.is_recently_fixed() for v in vulnerabilities):
            trend = 'improving'
        else:
            trend = 'stable'
        
        return {
            'level': level,
            'level_display': level_display,
            'total_vulnerabilities': len(vulnerabilities),
            'critical_count': severity_counts['critical'],
            'high_count': severity_counts['high'],
            'medium_count': severity_counts['medium'],
            'low_count': severity_counts['low'],
            'open_count': state_counts['open'],
            'fixed_count': state_counts['fixed'],
            'dismissed_count': state_counts['dismissed'],
            'categories': categories,
            'trend': trend
        }
    
    def get_vulnerability_trends(self, repo_full_name: str, days: int = 30) -> Dict:
        """
        Get vulnerability trends for the last N days
        
        Args:
            repo_full_name: Repository full name
            days: Number of days to analyze
            
        Returns:
            Dictionary with trend data
        """
        since = datetime.now(dt_timezone.utc) - timedelta(days=days)
        
        # Query vulnerabilities from the last N days
        vulnerabilities = CodeQLVulnerability.objects(
            repository_full_name=repo_full_name,
            created_at__gte=since
        ).order_by('created_at')
        
        # Group by day
        daily_counts = {}
        for vuln in vulnerabilities:
            day = vuln.created_at.date()
            if day not in daily_counts:
                daily_counts[day] = {'total': 0, 'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
            
            daily_counts[day]['total'] += 1
            daily_counts[day][vuln.severity] += 1
        
        return {
            'period_days': days,
            'daily_counts': daily_counts,
            'total_new_vulnerabilities': len(vulnerabilities)
        }


def get_codeql_service_for_user(user_id: int) -> Optional[CodeQLService]:
    """
    Get CodeQL service instance with user's GitHub token
    
    Args:
        user_id: User ID to get token for
        
    Returns:
        CodeQLService instance or None if no token available
    """
    token = GitHubTokenService.get_token_for_operation('code_scanning', user_id)
    if not token:
        token = GitHubTokenService._get_user_token(user_id)
    if not token:
        token = GitHubTokenService._get_oauth_app_token()
    
    if not token:
        logger.error(f"No GitHub token available for CodeQL analysis (user: {user_id})")
        return None
    
    return CodeQLService(token)