"""
Unified GitHub token management service

This service provides a unified interface for getting GitHub tokens based on required scopes.
It handles both OAuth App tokens (for basic operations) and user OAuth tokens (for repository access).
"""
import logging
from typing import Optional, Dict, List, Tuple
from django.utils import timezone
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GitHubTokenService:
    """
    Unified service for managing GitHub tokens based on required scopes
    
    This service determines which token to use based on the required scopes:
    - For basic operations (public repos, user info): OAuth App token
    - For repository access (private repos, commits): User OAuth token
    """
    
    # Scope definitions for different operations
    SCOPES = {
        'basic': [],  # No special scopes needed
        'public_repos': ['public_repo'],  # Access to public repositories
        'private_repos': ['repo'],  # Access to private repositories
        'user_info': ['user:email'],  # Access to user email
        'org_access': ['read:org'],  # Access to organization membership
        'code_scanning': ['security_events'],  # Access to CodeQL and security events
        'full_access': ['repo', 'user:email', 'read:org']  # Full access
    }
    
    @staticmethod
    def get_token_for_repository_or_org(repository_full_name: Optional[str] = None, organization: Optional[str] = None) -> Optional[str]:
        """Resolve token based on repository owner or explicit organization using GitHub App credentials.
        - If an active `IntegrationConfig` exists for the org with `app_id` and `private_key`,
          generate a short-lived Installation Access Token via the GitHub App flow and return it.
        - Otherwise, fallback to legacy OAuth App token (public-only), if configured.
        """
        try:
            if repository_full_name and not organization:
                try:
                    organization = repository_full_name.split('/', 1)[0]
                except Exception:
                    organization = None

            if organization:
                from management.models import IntegrationConfig
                integration = (
                    IntegrationConfig.objects
                    .filter(provider='github', github_organization=organization, status='active')
                    .first()
                )
                if integration and integration.app_id and integration.private_key:
                    token = GitHubTokenService._get_github_app_installation_token(
                        app_id=integration.app_id.strip(),
                        private_key_pem=integration.private_key.strip(),
                        organization=organization,
                    )
                    if token:
                        logger.info("Using GitHub App installation token for org %s", organization)
                        return token
        except Exception as e:
            logger.warning(f"Failed to resolve integration for org {organization}: {e}")

        # Fallback (public repos only if configured)
        return GitHubTokenService._get_oauth_app_token()
    
    @staticmethod
    def get_token_for_operation(operation_type: str, user_id: Optional[int] = None) -> Optional[str]:
        """
        Get the appropriate GitHub token for a specific operation
        
        Args:
            operation_type: Type of operation ('basic', 'public_repos', 'private_repos', 'user_info', 'org_access', 'full_access')
            user_id: User ID (required for user-scoped operations)
            
        Returns:
            GitHub token or None if not available
        """
        required_scopes = GitHubTokenService.SCOPES.get(operation_type, [])
        
        if not required_scopes:
            # Basic operations - use OAuth App token
            return GitHubTokenService._get_oauth_app_token()
        
        # For operations requiring user scopes, we need a user token
        if user_id:
            user_token = GitHubTokenService._get_user_token(user_id)
            if user_token:
                # Temporarily disable scope checking for testing
                # if GitHubTokenService._has_required_scopes(user_id, required_scopes):
                logger.info(f"Using user token for operation '{operation_type}' (user {user_id})")
                return user_token
            else:
                logger.warning(f"No valid user token found for operation '{operation_type}' (user {user_id})")
                return None
        
        # For operations requiring scopes but no user_id provided
        logger.warning(f"Operation '{operation_type}' requires user token but no user_id provided")
        return None
    
    @staticmethod
    def get_token_for_repository_access(user_id: int, repo_full_name: str) -> Optional[str]:
        """
        Get token for repository access (handles public vs private repos)
        
        Args:
            user_id: User ID
            repo_full_name: Repository name (owner/repo)
            
        Returns:
            GitHub token or None if not available
        """
        # First attempt: org-specific integration token
        org_token = GitHubTokenService.get_token_for_repository_or_org(repository_full_name=repo_full_name)
        if org_token:
            return org_token

        # Then try user token (works for both public and private repos)
        user_token = GitHubTokenService._get_user_token(user_id)
        if user_token and GitHubTokenService._has_required_scopes(user_id, ['repo']):
            logger.info(f"Using user token for repository access: {repo_full_name}")
            return user_token
        
        # For public repos, try OAuth App token
        oauth_token = GitHubTokenService._get_oauth_app_token()
        if oauth_token:
            # Check if repo is public (OAuth App can only access public repos)
            if GitHubTokenService._is_public_repository(repo_full_name, oauth_token):
                logger.info(f"Using OAuth App token for public repository: {repo_full_name}")
                return oauth_token
        
        logger.warning(f"No suitable token found for repository: {repo_full_name}")
        return None
    
    @staticmethod
    def get_token_for_api_call(user_id: int, api_endpoint: str) -> Optional[str]:
        """
        Get token for specific GitHub API endpoint
        
        Args:
            user_id: User ID
            api_endpoint: GitHub API endpoint (e.g., '/user/repos', '/repos/owner/repo/commits')
            
        Returns:
            GitHub token or None if not available
        """
        # Determine required scopes based on endpoint
        if '/user/repos' in api_endpoint or '/user' in api_endpoint:
            return GitHubTokenService.get_token_for_operation('private_repos', user_id)
        elif '/repos/' in api_endpoint:
            # Extract repo name from endpoint
            parts = api_endpoint.split('/repos/')
            if len(parts) > 1:
                repo_full_name = parts[1].split('/')[0] + '/' + parts[1].split('/')[1]
                # Try org integration first
                token = GitHubTokenService.get_token_for_repository_or_org(repository_full_name=repo_full_name)
                if token:
                    return token
                return GitHubTokenService.get_token_for_repository_access(user_id, repo_full_name)
        
        # Default to user token for most API calls
        return GitHubTokenService.get_token_for_operation('private_repos', user_id)
    
    @staticmethod
    def _get_oauth_app_token() -> Optional[str]:
        """Get OAuth App token (client_secret)"""
        try:
            from allauth.socialaccount.models import SocialApp
            
            github_app = SocialApp.objects.filter(provider='github').first()
            if not github_app or not github_app.secret:
                logger.debug("No OAuth App token available")
                return None
            
            logger.debug("Using OAuth App token")
            return github_app.secret
            
        except Exception as e:
            logger.error(f"Error getting OAuth App token: {e}")
            return None

    @staticmethod
    def _get_github_app_installation_token(app_id: str, private_key_pem: str, organization: str) -> Optional[str]:
        """Create a GitHub App JWT, find the installation for the org, and return an installation access token."""
        try:
            import requests
            import jwt
            from datetime import datetime, timedelta, timezone as dt_tz

            # Build JWT for the GitHub App
            now = datetime.now(dt_tz.utc)
            payload = {
                'iat': int((now - timedelta(seconds=60)).timestamp()),  # 60s skew
                'exp': int((now + timedelta(minutes=9)).timestamp()),    # <10 min
                'iss': app_id,
            }
            app_jwt = jwt.encode(payload, private_key_pem, algorithm='RS256')

            headers = {
                'Authorization': f'Bearer {app_jwt}',
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'GitPulse'
            }

            # Find installation for the organization
            installation_id = None
            page = 1
            while True:
                resp = requests.get(
                    'https://api.github.com/app/installations',
                    headers=headers,
                    params={'per_page': 100, 'page': page},
                    timeout=15,
                )
                resp.raise_for_status()
                installs = resp.json()
                for inst in installs:
                    account = inst.get('account') or {}
                    login = (account.get('login') or '').lower()
                    if login == (organization or '').lower():
                        installation_id = inst.get('id')
                        break
                if installation_id or not installs or len(installs) < 100:
                    break
                page += 1

            if not installation_id:
                logger.warning("No GitHub App installation found for org %s", organization)
                return None

            # Create installation access token
            token_resp = requests.post(
                f'https://api.github.com/app/installations/{installation_id}/access_tokens',
                headers=headers,
                timeout=15,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            token = token_data.get('token')
            if not token:
                logger.warning("GitHub did not return an installation token for org %s", organization)
                return None
            return token
        except Exception as e:
            logger.error(f"Error creating GitHub App installation token for org {organization}: {e}")
            return None
    
    @staticmethod
    def _get_user_token(user_id: int) -> Optional[str]:
        """Get user's OAuth token"""
        try:
            from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
            from django.contrib.auth.models import User
            
            user = User.objects.get(id=user_id)
            github_app = SocialApp.objects.filter(provider='github').first()
            
            if not github_app:
                return None
            
            social_account = SocialAccount.objects.filter(user=user, provider='github').first()
            if not social_account:
                return None
            
            social_token = SocialToken.objects.filter(account=social_account, app=github_app).first()
            if not social_token:
                return None
            
            # Check if token is expired
            if social_token.expires_at and social_token.expires_at <= timezone.now():
                logger.warning(f"User token expired for user {user_id}")
                return None
            
            logger.debug(f"Using user token for user {user_id}")
            return social_token.token
            
        except Exception as e:
            logger.error(f"Error getting user token for user {user_id}: {e}")
            return None
    
    @staticmethod
    def _has_required_scopes(user_id: int, required_scopes: List[str]) -> bool:
        """Check if user token has required scopes"""
        try:
            from analytics.github_utils import get_user_github_scopes
            
            user_scopes = get_user_github_scopes(user_id)
            if not user_scopes:
                return False
            
            # Check if all required scopes are present
            for scope in required_scopes:
                if scope not in user_scopes:
                    logger.debug(f"User {user_id} missing required scope: {scope}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking scopes for user {user_id}: {e}")
            return False
    
    @staticmethod
    def _is_public_repository(repo_full_name: str, token: str) -> bool:
        """Check if repository is public (OAuth App can access it)"""
        try:
            import requests
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            url = f"https://api.github.com/repos/{repo_full_name}"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                repo_data = response.json()
                return not repo_data.get('private', True)
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking repository visibility for {repo_full_name}: {e}")
            return False
    
    @staticmethod
    def validate_token_access(token: str, required_scopes: Optional[List[str]] = None) -> Dict[str, any]:
        """
        Validate token access and return detailed information
        
        Args:
            token: GitHub token to validate
            required_scopes: List of required scopes
            
        Returns:
            Dictionary with validation results
        """
        try:
            import requests
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Test basic access
            response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
            
            if response.status_code != 200:
                return {
                    'valid': False,
                    'error': f'Token validation failed: {response.status_code}',
                    'scopes': [],
                    'rate_limit': {}
                }
            
            # Get scopes from headers
            scopes_header = response.headers.get('X-OAuth-Scopes', '')
            scopes = [scope.strip() for scope in scopes_header.split(',') if scope.strip()]
            
            # Get rate limit info
            rate_limit = {
                'limit': int(response.headers.get('X-RateLimit-Limit', 0)),
                'remaining': int(response.headers.get('X-RateLimit-Remaining', 0)),
                'reset': int(response.headers.get('X-RateLimit-Reset', 0))
            }
            
            # Check if required scopes are met
            missing_scopes = []
            if required_scopes:
                missing_scopes = [scope for scope in required_scopes if scope not in scopes]
            
            return {
                'valid': True,
                'scopes': scopes,
                'missing_scopes': missing_scopes,
                'rate_limit': rate_limit,
                'user_info': response.json()
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'scopes': [],
                'rate_limit': {}
            }


# Backward compatibility functions
def get_github_token_for_user(user_id: int) -> Optional[str]:
    """
    Get GitHub token for API access - tries user token first, then app token
    
    Args:
        user_id: Django user ID
        
    Returns:
        GitHub token or None if not found
    """
    return GitHubTokenService.get_token_for_operation('private_repos', user_id)


def get_github_token_for_basic_operations() -> Optional[str]:
    """
    Get GitHub token for basic operations (public repos, user info)
    
    Returns:
        GitHub token or None if not found
    """
    return GitHubTokenService.get_token_for_operation('basic')


def get_github_token_for_repository(user_id: int, repo_full_name: str) -> Optional[str]:
    """
    Get GitHub token for repository access
    
    Args:
        user_id: User ID
        repo_full_name: Repository name (owner/repo)
        
    Returns:
        GitHub token or None if not found
    """
    return GitHubTokenService.get_token_for_repository_access(user_id, repo_full_name) 