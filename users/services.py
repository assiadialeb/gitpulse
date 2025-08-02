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
    
    def save_user_to_mongodb(self, user_data: Dict) -> GitHubUser:
        """Save or update GitHub user in MongoDB"""
        try:
            # Convert string dates to datetime objects
            if user_data.get('github_created_at'):
                user_data['github_created_at'] = datetime.fromisoformat(
                    user_data['github_created_at'].replace('Z', '+00:00')
                )
            if user_data.get('github_updated_at'):
                user_data['github_updated_at'] = datetime.fromisoformat(
                    user_data['github_updated_at'].replace('Z', '+00:00')
                )
            
            # Check if user already exists
            existing_user = GitHubUser.objects(github_id=user_data['github_id']).first()
            
            if existing_user:
                # Update existing user
                for key, value in user_data.items():
                    setattr(existing_user, key, value)
                existing_user.updated_at = datetime.now(timezone.utc)
                existing_user.save()
                logger.info(f"Updated existing GitHubUser: {user_data['login']}")
                return existing_user
            else:
                # Create new user
                user_data['created_at'] = datetime.now(timezone.utc)
                user_data['updated_at'] = datetime.now(timezone.utc)
                github_user = GitHubUser(**user_data)
                github_user.save()
                logger.info(f"Created new GitHubUser: {user_data['login']}")
                return github_user
            
        except Exception as e:
            logger.error(f"Error saving GitHub user to MongoDB: {str(e)}")
            raise
    
    def sync_user_data(self, username: str) -> GitHubUser:
        """Sync user data from GitHub and save to MongoDB"""
        user_data = self.get_user_info(username)
        return self.save_user_to_mongodb(user_data) 

    def get_authenticated_user_organizations(self) -> list:
        """Get all organizations for the authenticated user via GitHub API"""
        orgs_url = "https://api.github.com/user/orgs"
        orgs, _ = self._make_request(orgs_url)
        return orgs if isinstance(orgs, list) else [] 