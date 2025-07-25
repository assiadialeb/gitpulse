"""
Utilities for GitHub OAuth App token management
"""
from typing import Optional
from github.models import GitHubApp
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def get_github_token_for_user(user_id: int) -> Optional[str]:
    """
    Get GitHub token for API access - tries user token first, then app token
    
    Args:
        user_id: Django user ID
        
    Returns:
        GitHub token or None if not found
    """
    try:
        from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
        from django.contrib.auth.models import User
        
        # Try to get user's OAuth token first (for /user/repos access)
        try:
            user = User.objects.get(id=user_id)
            github_app = SocialApp.objects.filter(provider='github').first()
            
            if github_app:
                social_account = SocialAccount.objects.filter(user=user, provider='github').first()
                if social_account:
                    social_token = SocialToken.objects.filter(account=social_account, app=github_app).first()
                    if social_token:
                        if not social_token.expires_at or social_token.expires_at > timezone.now():
                            logger.info(f"Using user OAuth token for user {user_id}")
                            return social_token.token
                        else:
                            logger.warning(f"User OAuth token expired for user {user_id}")
        except Exception as e:
            logger.info(f"No user OAuth token for user {user_id}: {e}")
        
        # Fallback to app token
        logger.info(f"Using app token for user {user_id}")
        return get_github_oauth_app_token()
        
    except Exception as e:
        logger.error(f"Error getting GitHub token for user {user_id}: {e}")
        return None


def get_user_github_scopes(user_id: int) -> list:
    """
    Get the scopes available for a user's GitHub token
    
    Args:
        user_id: Django user ID
        
    Returns:
        List of scopes or empty list if no token
    """
    try:
        from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
        from django.contrib.auth.models import User
        import requests
        
        user = User.objects.get(id=user_id)
        github_app = SocialApp.objects.filter(provider='github').first()
        
        if github_app:
            social_account = SocialAccount.objects.filter(user=user, provider='github').first()
            if social_account:
                social_token = SocialToken.objects.filter(account=social_account, app=github_app).first()
                if social_token:
                    # Test the token to get scopes
                    headers = {
                        'Authorization': f'token {social_token.token}',
                        'Accept': 'application/vnd.github.v3+json'
                    }
                    response = requests.get('https://api.github.com/user', headers=headers)
                    if response.status_code == 200:
                        scopes = response.headers.get('X-OAuth-Scopes', '')
                        return [scope.strip() for scope in scopes.split(',') if scope.strip()]
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting user GitHub scopes for user {user_id}: {e}")
        return []


def ensure_github_oauth_scopes():
    """
    Ensure GitHub OAuth App is configured with the right scopes
    
    This function checks and updates the allauth SocialApp configuration
    to request the necessary scopes for repository access.
    """
    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        
        # Get or create GitHub SocialApp
        site = Site.objects.get_current()
        github_app, created = SocialApp.objects.get_or_create(
            provider='github',
            defaults={
                'name': 'GitHub',
                'client_id': '',
                'secret': ''
            }
        )
        
        # Ensure the app is associated with the current site
        if site not in github_app.sites.all():
            github_app.sites.add(site)
        
        # Update settings to request the right scopes
        from django.conf import settings
        
        # Ensure SOCIALACCOUNT_PROVIDERS includes GitHub with proper scopes
        providers = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {})
        
        github_config = providers.get('github', {})
        github_config['SCOPE'] = [
            'user:email',  # Access to user email
            'repo',        # Access to repositories (public and private)
            'read:org'     # Read organization membership
        ]
        
        providers['github'] = github_config
        
        # Note: This would need to be set in settings.py permanently
        logger.info("GitHub OAuth scopes configured: user:email, repo, read:org")
        logger.info("Make sure to add these scopes to your settings.py SOCIALACCOUNT_PROVIDERS")
        
        return github_app
        
    except Exception as e:
        logger.error(f"Error configuring GitHub OAuth scopes: {e}")
        return None


def sync_github_app_with_oauth():
    """
    Synchronize GitHubApp model with SocialApp for unified configuration
    
    This ensures both models have the same client_id and secret,
    allowing for a single configuration point.
    """
    try:
        from allauth.socialaccount.models import SocialApp
        from github.models import GitHubApp
        
        # Get SocialApp
        social_app = SocialApp.objects.filter(provider='github').first()
        if not social_app:
            logger.error("No GitHub SocialApp found")
            return False
        
        # Get or create GitHubApp
        github_app, created = GitHubApp.objects.get_or_create(
            client_id=social_app.client_id,
            defaults={'client_secret': social_app.secret or ''}
        )
        
        # Sync the secret if different
        if github_app.client_secret != social_app.secret:
            github_app.client_secret = social_app.secret or ''
            github_app.save()
            logger.info("Synchronized GitHubApp with SocialApp")
        
        return True
        
    except Exception as e:
        logger.error(f"Error synchronizing GitHub configurations: {e}")
        return False


def get_github_oauth_app_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Get GitHub OAuth App credentials (client_id, client_secret)
    
    Returns:
        Tuple of (client_id, client_secret) or (None, None) if not found
    """
    try:
        from allauth.socialaccount.models import SocialApp
        
        github_app = SocialApp.objects.filter(provider='github').first()
        if not github_app:
            logger.error("No GitHub SocialApp found")
            return None, None
        
        if not github_app.client_id or not github_app.secret:
            logger.error("OAuth App client_id or client_secret missing")
            return None, None
        
        logger.info("Using OAuth App client credentials")
        return github_app.client_id, github_app.secret
        
    except Exception as e:
        logger.error(f"Error getting OAuth App credentials: {e}")
        return None, None


def get_github_oauth_app_token() -> Optional[str]:
    """
    Get GitHub token using OAuth App configuration
    
    Returns:
        GitHub client_secret (used as token) or None if failed
    """
    try:
        from allauth.socialaccount.models import SocialApp
        
        github_app = SocialApp.objects.filter(provider='github').first()
        if not github_app:
            logger.error("No GitHub SocialApp found")
            return None
        
        if not github_app.secret:
            logger.error("No OAuth App secret configured")
            return None
        
        logger.info("Using OAuth App client_secret as token")
        return github_app.secret
        
    except Exception as e:
        logger.error(f"Error getting OAuth App token: {e}")
        return None


def get_github_token() -> Optional[str]:
    """
    Get GitHub token for API access (simplified version without user_id)
    
    Returns:
        GitHub OAuth App token or None if not found
    """
    logger.info("Getting OAuth App token")
    return get_github_oauth_app_token()


def get_github_app_installation_token(installation_id: int) -> Optional[str]:
    """
    Get GitHub App installation token (for organization-wide access)
    
    Args:
        installation_id: GitHub App installation ID
        
    Returns:
        Installation access token or None if failed
    """
    try:
        import jwt
        import time
        import requests
        from datetime import datetime, timedelta
        
        github_app = GitHubApp.objects.first()
        if not github_app:
            logger.error("No GitHub App configuration found")
            return None
        
        # For GitHub Apps, client_secret should be the private key
        private_key = github_app.client_secret
        app_id = github_app.client_id
        
        # Generate JWT for GitHub App authentication
        now = int(time.time())
        payload = {
            'iat': now - 60,  # Issued at time (60 seconds ago to account for clock skew)
            'exp': now + (10 * 60),  # Expiration time (10 minutes from now)
            'iss': app_id  # Issuer (GitHub App ID)
        }
        
        # Create JWT
        jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
        
        # Get installation access token
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitPulse/1.0'
        }
        
        url = f'https://api.github.com/app/installations/{installation_id}/access_tokens'
        response = requests.post(url, headers=headers)
        
        if response.status_code == 201:
            token_data = response.json()
            logger.info(f"Got installation token for installation {installation_id}")
            return token_data['token']
        else:
            logger.error(f"Failed to get installation token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error getting GitHub App installation token: {e}")
        return None


