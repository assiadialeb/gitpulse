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
            
            # Debug info
            messages.info(request, f'GitHubApp: ID={github_app.client_id[:10]}..., PAT={github_app.client_secret[:10]}...')
            messages.info(request, f'SocialApp: ID={social_app.client_id[:10]}..., Secret={social_app.secret[:10] if social_app.secret else "None"}...')
            
            return redirect('github:admin')
    else:
        form = GitHubAppForm(instance=github_app)

    # Check if app has valid token for API access
    app_token_valid = False
    app_username = None
    if github_app.client_secret:
        try:
            # Test if it's a Personal Access Token
            if github_app.client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
                test_headers = {
                    'Authorization': f'token {github_app.client_secret}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'GitPulse/1.0'
                }
                test_response = requests.get('https://api.github.com/user', headers=test_headers, timeout=10)
                if test_response.status_code == 200:
                    user_data = test_response.json()
                    app_token_valid = True
                    app_username = user_data.get('login')
            else:
                # For OAuth App client_secret, we can't test /user endpoint directly
                # But we can test rate limit endpoint which works with any valid credentials
                test_headers = {
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'GitPulse/1.0'
                }
                # Test basic API access (rate limit endpoint doesn't need auth)
                test_response = requests.get('https://api.github.com/rate_limit', headers=test_headers, timeout=10)
                if test_response.status_code == 200:
                    # OAuth App configured (we can't test user endpoint without OAuth flow)
                    app_token_valid = True
                    app_username = "OAuth App configured"
        except Exception as e:
            print(f"API test error: {e}")  # Debug

    github_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
    
    context = {
        'form': form,
        'oauth_secret': social_app.secret if social_app.secret else '',
        'user_redirect_url': request.build_absolute_uri('/accounts/github/login/callback/'),
        'github_connected': github_account is not None,
        'github_username': github_account.extra_data.get('login') if github_account else None,
        'app_token_valid': app_token_valid,
        'app_username': app_username,
    }
    return render(request, 'github/admin_simple.html', context)