"""
GitHub API service for fetching commit data
"""
import requests
import time
from datetime import datetime, timezone as dt_timezone
from typing import List, Dict, Optional, Tuple
from django.conf import settings
import logging
from allauth.socialaccount.models import SocialToken
from django.contrib.auth import get_user_model


logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors"""
    pass


class GitHubRateLimitError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is exceeded"""
    pass


# Fonction supprimée - utiliser get_github_token_for_user depuis github_utils.py


class GitHubService:
    """Service for interacting with GitHub API to fetch commit data"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {access_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitPulse/1.0'
        })
        
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Tuple[Dict, Dict]:
        """
        Make a request to GitHub API with error handling and rate limiting
        
        Returns:
            Tuple of (response_data, headers)
        """
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            # Check rate limit
            rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
            rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
            
            if rate_limit_remaining < 5:  # More conservative threshold
                reset_time = datetime.fromtimestamp(rate_limit_reset, dt_timezone.utc)
                logger.warning(f"GitHub rate limit low: {rate_limit_remaining} requests remaining. Resets at {reset_time}")
                
                if rate_limit_remaining == 0:
                    wait_time = max(0, rate_limit_reset - time.time() + 60)  # Add 1 minute buffer
                    raise GitHubRateLimitError(f"Rate limit exceeded. Retry after {wait_time} seconds")
            
            if response.status_code == 403 and 'rate limit' in response.text.lower():
                raise GitHubRateLimitError("Rate limit exceeded")
            
            if response.status_code == 404:
                # For releases endpoint, 404 might just mean no releases exist
                if '/releases' in url:
                    return [], dict(response.headers)
                else:
                    raise GitHubAPIError(f"Repository not found or not accessible: {url}")
            
            if not response.ok:
                raise GitHubAPIError(f"GitHub API error {response.status_code}: {response.text}")
            
            return response.json(), dict(response.headers)
            
        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}")
    
    def get_commits(self, repo_full_name: str, since: Optional[datetime] = None, 
                   until: Optional[datetime] = None, per_page: int = 100) -> List[Dict]:
        """
        Fetch commits from a repository with pagination
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            since: Only commits after this date (optional)
            until: Only commits before this date (optional)
            per_page: Number of commits per page (max 100)
            
        Returns:
            List of commit dictionaries
        """
        commits = []
        url = f"{self.base_url}/repos/{repo_full_name}/commits"
        page = 1
        api_calls = 0
        
        params = {
            'per_page': min(per_page, 100),
            'page': page
        }
        
        if since:
            params['since'] = since.isoformat()
        if until:
            params['until'] = until.isoformat()
            
        logger.info(f"Fetching commits for {repo_full_name} with params: {params}")
        
        while True:
            params['page'] = page
            data, headers = self._make_request(url, params)
            api_calls += 1
            
            if not data:
                break
                
            commits.extend(data)
            logger.info(f"Page {page}: Fetched {len(data)} commits. Total: {len(commits)}")
            
            # Check if there are more pages
            link_header = headers.get('Link', '')
            if 'rel="next"' not in link_header:
                break
                
            page += 1
            
            # Safety check to prevent infinite loops
            if page > 1000:  # Arbitrary large number
                logger.warning(f"Reached maximum page limit for {repo_full_name}")
                break
        
        logger.info(f"Finished fetching commits for {repo_full_name}. Total: {len(commits)}, API calls: {api_calls}")
        return commits
    
    def get_commit_details(self, repo_full_name: str, commit_sha: str) -> Dict:
        """
        Get detailed information about a specific commit including file changes
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            commit_sha: Commit SHA hash
            
        Returns:
            Detailed commit dictionary with file changes
        """
        url = f"{self.base_url}/repos/{repo_full_name}/commits/{commit_sha}"
        data, _ = self._make_request(url)
        return data
    
    def parse_commit_data(self, commit_data: Dict, repo_full_name: str, application_id: int) -> Dict:
        """
        Parse GitHub commit data into our internal format
        """
        commit = commit_data.get('commit', {})
        author = commit.get('author', {})
        committer = commit.get('committer', {})
        stats = commit_data.get('stats', {})

        # Parse file changes
        files_changed = []
        for file_data in commit_data.get('files', []):
            file_change = {
                'filename': file_data.get('filename', ''),
                'additions': file_data.get('additions', 0),
                'deletions': file_data.get('deletions', 0),
                'changes': file_data.get('changes', 0),
                'status': file_data.get('status', 'modified'),
                'patch': file_data.get('patch', '')[:5000]  # Limit patch size
            }
            files_changed.append(file_change)

        # Parse dates
        authored_date = datetime.fromisoformat(author.get('date', '').replace('Z', '+00:00'))
        committed_date = datetime.fromisoformat(committer.get('date', '').replace('Z', '+00:00'))

        # --- Ajout récupération info PR ---
        pull_request_number = None
        pull_request_url = None
        pull_request_merged_at = None
        try:
            pr_url = f"{self.base_url}/repos/{repo_full_name}/commits/{commit_data.get('sha')}/pulls"
            prs, _ = self._make_request(pr_url, params={"per_page": 1})
            if prs and isinstance(prs, list) and len(prs) > 0:
                pr = prs[0]
                pull_request_number = pr.get('number')
                pull_request_url = pr.get('html_url')
                pull_request_merged_at = pr.get('merged_at')
                if pull_request_merged_at:
                    pull_request_merged_at = datetime.fromisoformat(pull_request_merged_at.replace('Z', '+00:00'))
        except Exception as e:
            pass
        # --- Fin ajout PR ---

        parsed_data = {
            'sha': commit_data.get('sha'),
            'repository_full_name': repo_full_name,
            'application_id': application_id,
            'message': commit.get('message', ''),
            'author_name': author.get('name', ''),
            'author_email': author.get('email', ''),
            'committer_name': committer.get('name', ''),
            'committer_email': committer.get('email', ''),
            'authored_date': authored_date,
            'committed_date': committed_date,
            'additions': stats.get('additions', 0),
            'deletions': stats.get('deletions', 0),
            'total_changes': stats.get('total', 0),
            'files_changed': files_changed,
            'parent_shas': [parent.get('sha') for parent in commit_data.get('parents', [])],
            'tree_sha': commit.get('tree', {}).get('sha'),
            'url': commit_data.get('html_url', ''),
            'synced_at': datetime.now(dt_timezone.utc),
            # Champs PR
            'pull_request_number': pull_request_number,
            'pull_request_url': pull_request_url,
            'pull_request_merged_at': pull_request_merged_at,
        }

        return parsed_data
    
    def get_rate_limit_info(self) -> Dict:
        """Get current rate limit information"""
        url = f"{self.base_url}/rate_limit"
        data, _ = self._make_request(url)
        return data 