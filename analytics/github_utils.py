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
    Get GitHub token for API access - unified OAuth App approach
    
    This function implements a unified approach where:
    1. Users authenticate via OAuth App (allauth)
    2. We use their OAuth tokens for API access
    3. Fallback to admin PAT if no user token available
    
    Args:
        user_id: Django user ID
        
    Returns:
        GitHub access token string or None if not found
    """
    try:
        from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
        from django.contrib.auth.models import User
        
        # Strategy 1: User's OAuth token from allauth (PREFERRED)
        try:
            user = User.objects.get(id=user_id)
            
            # Get the GitHub SocialApp (OAuth App configuration)
            github_app = SocialApp.objects.filter(provider='github').first()
            if not github_app:
                logger.warning("No GitHub SocialApp configured for allauth")
            else:
                # Get user's GitHub account
                social_account = SocialAccount.objects.filter(
                    user=user,
                    provider='github'
                ).first()
                
                if social_account:
                    # Get the OAuth token for this user
                    social_token = SocialToken.objects.filter(
                        account=social_account,
                        app=github_app
                    ).first()
                    
                    if social_token:
                        # Check if token is still valid
                        if not social_token.expires_at or social_token.expires_at > timezone.now():
                            logger.info(f"Using user OAuth token for user {user_id} ({user.username})")
                            return social_token.token
                        else:
                            logger.warning(f"User OAuth token expired for user {user_id}")
                    else:
                        logger.info(f"No OAuth token found for user {user_id}")
                else:
                    logger.info(f"User {user_id} has not connected their GitHub account")
                    
        except User.DoesNotExist:
            logger.error(f"User {user_id} does not exist")
        except Exception as e:
            logger.error(f"Error getting user OAuth token for user {user_id}: {e}")
        
        # Strategy 2: Fallback to admin PAT (for background tasks or when user not connected)
        logger.info(f"Falling back to admin PAT for user {user_id}")
        admin_token = get_github_oauth_app_token()
        if admin_token:
            logger.info(f"Using admin PAT as fallback for user {user_id}")
            return admin_token
        
        logger.error(f"No GitHub token available for user {user_id}")
        return None
        
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
        
        # Check if client_secret is actually a Personal Access Token (hack/fallback)
        if client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
            logger.info("Using Personal Access Token stored in client_secret (fallback mode)")
            return client_secret
        
        # If it's a real OAuth App client_secret, we can't use it directly for API calls
        # OAuth Apps need the OAuth flow to get access tokens
        logger.warning("OAuth App client_secret detected but no user tokens available")
        logger.warning("OAuth Apps require user authorization flow for API access")
        logger.warning("Consider one of these solutions:")
        logger.warning("1. Use GitHub App (not OAuth App) for organization-wide access")
        logger.warning("2. Store a Personal Access Token in client_secret field (current fallback)")
        logger.warning("3. Implement proper OAuth flow for user tokens")
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting OAuth App token: {e}")
        return None


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


