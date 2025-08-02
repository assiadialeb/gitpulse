"""
Services for GitHub user data retrieval
"""
import requests
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from django.conf import settings
from github.models import GitHubToken
# from models import GitHubUser  # Removed - using Django models instead

logger = logging.getLogger(__name__)


class GitHubUserService:
    """Service for retrieving GitHub user information"""
    
    def __init__(self, user_id: int):
        """Initialize service with user's GitHub token"""
        self.user_id = user_id
        self.github_token = None
        self._init_token()
    
    def _init_token(self):
        """Initialize GitHub token from user"""
        try:
            token_obj = GitHubToken.objects.get(user_id=self.user_id)
            self.github_token = token_obj.access_token
        except GitHubToken.DoesNotExist:
            raise ValueError(f"No GitHub token found for user {self.user_id}")
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Tuple[Dict, Dict]:
        """Make authenticated request to GitHub API"""
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitPulse/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 404:
                raise ValueError(f"GitHub user not found: {url}")
            
            if not response.ok:
                raise ValueError(f"GitHub API error {response.status_code}: {response.text}")
            
            return response.json(), dict(response.headers)
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Request failed: {str(e)}")
    
    def get_user_info(self, username: str) -> Dict:
        """Get comprehensive user information from GitHub"""
        user_data = {}
        
        try:
            # Get basic user info
            user_url = f"https://api.github.com/users/{username}"
            user_info, headers = self._make_request(user_url)
            
            # Get user emails (requires authentication)
            emails_url = f"https://api.github.com/user/emails"
            emails_info, _ = self._make_request(emails_url)
            
            # Combine data
            user_data = {
                'github_id': user_info['id'],
                'login': user_info['login'],
                'name': user_info.get('name'),
                'email': user_info.get('email'),
                'avatar_url': user_info.get('avatar_url'),
                'bio': user_info.get('bio'),
                'company': user_info.get('company'),
                'blog': user_info.get('blog'),
                'location': user_info.get('location'),
                'hireable': user_info.get('hireable', False),
                'public_repos': user_info.get('public_repos', 0),
                'public_gists': user_info.get('public_gists', 0),
                'followers': user_info.get('followers', 0),
                'following': user_info.get('following', 0),
                'github_created_at': user_info.get('created_at'),
                'github_updated_at': user_info.get('updated_at'),
                'emails': emails_info
            }
            
            logger.info(f"Successfully retrieved GitHub data for user {username}")
            return user_data
            
        except Exception as e:
            logger.error(f"Error retrieving GitHub data for {username}: {str(e)}")
            raise
    
    # def save_user_to_mongodb(self, user_data: Dict) -> GitHubUser:
    #     """Save or update GitHub user in MongoDB - DEPRECATED"""
    #     # This method is deprecated as we no longer use MongoDB for user data
    #     pass
    
    # def sync_user_data(self, username: str) -> GitHubUser:
    #     """Sync user data from GitHub and save to MongoDB - DEPRECATED"""
    #     # This method is deprecated as we no longer use MongoDB for user data
    #     pass 

    def get_authenticated_user_organizations(self) -> list:
        """Get all organizations for the authenticated user via GitHub API"""
        orgs_url = "https://api.github.com/user/orgs"
        orgs, _ = self._make_request(orgs_url)
        return orgs if isinstance(orgs, list) else [] 