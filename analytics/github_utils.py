"""
Utilities for GitHub OAuth App token management
"""
from typing import Optional
from github.models import GitHubApp
import logging

logger = logging.getLogger(__name__)


def get_github_token_for_user(user_id: int) -> Optional[str]:
    """
    Get GitHub token for API access using OAuth App credentials
    
    Args:
        user_id: Django user ID
        
    Returns:
        GitHub access token string or None if not found
    """
    try:
        # Use OAuth App with client credentials
        return get_github_oauth_app_token()
        
    except Exception as e:
        logger.error(f"Error getting GitHub token for user {user_id}: {e}")
        return None


def get_github_oauth_app_token() -> Optional[str]:
    """
    Get GitHub token using OAuth App configuration
    
    Returns:
        GitHub access token or None if failed
    """
    try:
        # Get GitHub OAuth App configuration
        github_app = GitHubApp.objects.first()
        if not github_app:
            logger.error("No GitHub OAuth App configuration found")
            logger.error("Please configure your OAuth App in /admin/github/githubapp/")
            return None
        
        client_id = github_app.client_id
        client_secret = github_app.client_secret
        
        if not client_id or not client_secret:
            logger.error("GitHub client_id or client_secret missing")
            return None
        
        # Check if client_secret is actually a Personal Access Token
        if client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
            logger.info("Using Personal Access Token stored in client_secret")
            return client_secret
        
        # If it's a real OAuth App client_secret, we can't use it directly for API calls
        # OAuth Apps need the OAuth flow to get access tokens
        logger.info("OAuth App client_secret detected")
        logger.info("For API access with OAuth Apps, you need to:")
        logger.info("1. Use the OAuth flow to get user access tokens, OR")
        logger.info("2. Store a Personal Access Token in the client_secret field")
        
        # For now, return the client_secret - it might work for some basic operations
        # But recommend using a PAT for full functionality
        logger.warning("Returning client_secret - limited functionality expected")
        logger.warning("Consider using a Personal Access Token for full API access")
        
        return client_secret
        
    except Exception as e:
        logger.error(f"Error getting OAuth App token: {e}")
        return None


