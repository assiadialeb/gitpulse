import os
import secrets
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp, SocialAccount
from .forms import SocialAppForm, GitHubAppForm
from .models import GitHubApp


@login_required
def admin_view(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Superuser required.')
        return redirect('users:dashboard')

    # Handle GitHub OAuth App (single app for both user SSO and application access)
    github_app = GitHubApp.objects.first()
    if not github_app:
        github_app = GitHubApp.objects.create(
            client_id='',
            client_secret='',
        )
    
    # Handle SocialApp (sync with GitHubApp for user SSO)
    site = Site.objects.get_current()
    social_app = SocialApp.objects.filter(provider='github', sites=site).first()
    if not social_app:
        social_app = SocialApp.objects.create(provider='github', name='GitHub')
        social_app.sites.set([site])
    
    if request.method == 'POST':
        form = GitHubAppForm(request.POST, instance=github_app)
        oauth_secret = request.POST.get('oauth_secret', '')
        
        if form.is_valid():
            github_app = form.save()
            
            # Update SocialApp with OAuth credentials (for user SSO)
            social_app.client_id = github_app.client_id
            if oauth_secret:  # Only update if provided
                social_app.secret = oauth_secret
                social_app.save()
                messages.success(request, f'GitHub configuration saved! OAuth secret: {oauth_secret[:10]}...')
            else:
                messages.warning(request, 'GitHub configuration saved but no OAuth secret provided')
            
            # Sync GitHubApp with SocialApp (keep them in sync)
            github_app.client_secret = oauth_secret or github_app.client_secret
            github_app.save()
            
            return redirect('github:admin')
    else:
        form = GitHubAppForm(instance=github_app)

    # Check OAuth App configuration status
    oauth_configured = bool(social_app.client_id and social_app.secret)
    
    # Check if current user has GitHub connection with valid token
    user_github_connected = False
    user_github_username = None
    user_has_valid_token = False
    
    try:
        from analytics.github_utils import get_github_token_for_user, get_user_github_scopes
        
        # Check if user has GitHub account connected
        github_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
        if github_account:
            user_github_connected = True
            user_github_username = github_account.extra_data.get('login')
            
            # Check if user has valid OAuth token
            token = get_github_token_for_user(request.user.id)
            if token:  # OAuth App token is always valid if present
                user_has_valid_token = True
                
    except Exception as e:
        print(f"User token check error: {e}")  # Debug

    # Check if GitHub provider exists (for template safety)
    github_provider_exists = SocialApp.objects.filter(provider='github').exists()
    
    context = {
        'form': form,
        'oauth_secret': social_app.secret if social_app.secret else '',
        'user_redirect_url': request.build_absolute_uri('/accounts/github/login/callback/'),
        'oauth_configured': oauth_configured,
        'github_connected': user_github_connected,
        'github_username': user_github_username,
        'user_has_valid_token': user_has_valid_token,
        'github_provider_exists': github_provider_exists,
    }
    return render(request, 'github/admin_simple.html', context)


def admin_simple(request):
    """
    Simple GitHub configuration interface (alias for admin_view)
    """
    return admin_view(request)


def token_help(request):
    """
    GitHub token configuration help page
    """
    return render(request, 'github/token_help.html')


from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

@require_http_methods(["POST"])
def test_github_access(request):
    """
    Test GitHub token access via AJAX
    """
    try:
        from analytics.github_utils import get_github_token_for_user
        
        import requests
        
        token = get_github_token_for_user(request.user.id)
        if not token:
            return JsonResponse({
                'success': False,
                'error': 'Aucun token GitHub configuré'
            })
        
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Test user info
        response = requests.get('https://api.github.com/user', headers=headers)
        if response.status_code != 200:
            return JsonResponse({
                'success': False,
                'error': f'Token invalide (code {response.status_code})'
            })
        
        user_info = response.json()
        scopes = response.headers.get('X-OAuth-Scopes', '')
        
        # Test repository access
        total_repos = 0
        accessible_repos = 0
        
        # Application model no longer exists, test with repositories directly
        from repositories.models import Repository
        repos = Repository.objects.all()[:5]
        for repo in repos:
            total_repos += 1
            repo_name = repo.full_name
            
            try:
                url = f"https://api.github.com/repos/{repo_name}"
                repo_response = requests.get(url, headers=headers)
                if repo_response.status_code == 200:
                    accessible_repos += 1
            except:
                pass
        
        if total_repos == 0:
            return JsonResponse({
                'success': True,
                'message': 'Token configuré correctement (aucun repository à tester)',
                'user': user_info.get('login'),
                'scopes': scopes,
                'total_repos': 0,
                'accessible_repos': 0
            })
        
        success = accessible_repos > 0
        return JsonResponse({
            'success': success,
            'user': user_info.get('login'),
            'scopes': scopes,
            'total_repos': total_repos,
            'accessible_repos': accessible_repos,
            'error': f'Aucun repository accessible sur {total_repos} testés' if not success else None
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error checking permissions: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@login_required
def force_github_reauth(request):
    """
    Force GitHub re-authentication to get new scopes
    """
    try:
        from allauth.socialaccount.models import SocialAccount, SocialToken
        
        # Delete existing GitHub connection to force re-auth
        social_accounts = SocialAccount.objects.filter(user=request.user, provider='github')
        tokens_deleted = 0
        accounts_deleted = 0
        
        for account in social_accounts:
            # Delete associated tokens
            tokens = SocialToken.objects.filter(account=account)
            tokens_deleted += tokens.count()
            tokens.delete()
            
            # Delete account
            account.delete()
            accounts_deleted += 1
        
        messages.success(
            request, 
            f'GitHub connection reset ({accounts_deleted} accounts, {tokens_deleted} tokens deleted). '
            'Please reconnect to grant new permissions.'
        )
        
        # Redirect to GitHub OAuth with new scopes
        from django.urls import reverse
        from allauth.socialaccount.providers.github.urls import urlpatterns
        return redirect('github_login')  # This will use the new scopes from settings
        
    except Exception as e:
        messages.error(request, f'Error resetting GitHub connection: {e}')
        return redirect('github:admin')


def github_connection_status(request):
    """
    Check GitHub connection status and scopes for current user
    """
    try:
        from analytics.github_utils import get_user_github_scopes
        from allauth.socialaccount.models import SocialAccount
        
        # Check if user has GitHub account connected
        github_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
        
        if not github_account:
            return JsonResponse({
                'connected': False,
                'message': 'No GitHub account connected'
            })
        
        # Get user's current scopes
        scopes = get_user_github_scopes(request.user.id)
        required_scopes = ['user:email', 'repo', 'read:org']
        missing_scopes = [scope for scope in required_scopes if scope not in scopes]
        
        return JsonResponse({
            'connected': True,
            'username': github_account.extra_data.get('login'),
            'scopes': scopes,
            'required_scopes': required_scopes,
            'missing_scopes': missing_scopes,
            'has_all_scopes': len(missing_scopes) == 0
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error getting token scopes: {e}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)


def unified_setup(request):
    """
    Unified GitHub setup page
    """
    return render(request, 'github/unified_setup.html')