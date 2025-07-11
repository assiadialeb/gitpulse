import os
import secrets
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import GitHubApp, GitHubToken, GitHubOAuthState
from .forms import GitHubAppForm


@login_required
def oauth_start(request):
    """Start OAuth2 flow - redirect to GitHub"""
    try:
        github_app = GitHubApp.objects.first()
        if not github_app:
            messages.error(request, 'GitHub App not configured. Please contact administrator.')
            return redirect('users:dashboard')
        
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)
        GitHubOAuthState.objects.create(user=request.user, state=state)
        
        # Build OAuth2 authorization URL
        redirect_uri = request.build_absolute_uri(reverse('github:callback'))
        auth_url = (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={github_app.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope=repo,user&"
            f"state={state}"
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        messages.error(request, f'Error starting OAuth flow: {str(e)}')
        return redirect('users:dashboard')


@login_required
def oauth_callback(request):
    """Handle OAuth2 callback from GitHub"""
    try:
        # Verify state parameter
        state = request.GET.get('state')
        if not state:
            messages.error(request, 'Missing state parameter')
            return redirect('users:dashboard')
        
        oauth_state = get_object_or_404(GitHubOAuthState, state=state, user=request.user)
        if oauth_state.is_expired:
            oauth_state.delete()
            messages.error(request, 'OAuth state expired. Please try again.')
            return redirect('users:dashboard')
        
        # Clean up state
        oauth_state.delete()
        
        # Check for authorization code
        code = request.GET.get('code')
        if not code:
            error = request.GET.get('error')
            error_description = request.GET.get('error_description', 'Unknown error')
            messages.error(request, f'OAuth error: {error} - {error_description}')
            return redirect('users:dashboard')
        
        # Exchange code for access token
        github_app = GitHubApp.objects.first()
        if not github_app:
            messages.error(request, 'GitHub App not configured')
            return redirect('users:dashboard')
        
        token_response = requests.post(
            'https://github.com/login/oauth/access_token',
            data={
                'client_id': github_app.client_id,
                'client_secret': github_app.client_secret,
                'code': code,
                'redirect_uri': request.build_absolute_uri(reverse('github:callback'))
            },
            headers={'Accept': 'application/json'}
        )
        
        if token_response.status_code != 200:
            messages.error(request, 'Failed to exchange authorization code for token')
            return redirect('users:dashboard')
        
        token_data = token_response.json()
        
        if 'error' in token_data:
            messages.error(request, f'Token exchange error: {token_data.get("error_description", "Unknown error")}')
            return redirect('users:dashboard')
        
        access_token = token_data.get('access_token')
        if not access_token:
            messages.error(request, 'No access token received')
            return redirect('users:dashboard')
        
        # Get user info from GitHub
        user_response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
        )
        
        if user_response.status_code != 200:
            messages.error(request, 'Failed to get user info from GitHub')
            return redirect('users:dashboard')
        
        user_data = user_response.json()
        
        # Récupérer l'email principal si non présent dans /user
        github_email = user_data.get('email', '')
        if not github_email:
            emails_response = requests.get(
                'https://api.github.com/user/emails',
                headers={
                    'Authorization': f'token {access_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                # Prendre le premier email principal et vérifié
                primary_email = next((e['email'] for e in emails if e.get('primary') and e.get('verified')), None)
                if primary_email:
                    github_email = primary_email
                elif emails:
                    github_email = emails[0]['email']
        
        # Save or update token
        token, created = GitHubToken.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': access_token,
                'token_type': 'bearer',
                'scope': token_data.get('scope', ''),
                'expires_at': timezone.now() + timezone.timedelta(hours=1),  # GitHub tokens don't expire by default
                'github_user_id': user_data['id'],
                'github_username': user_data['login'],
                'github_email': github_email or ''
            }
        )
        
        if created:
            messages.success(request, f'Successfully connected to GitHub as {user_data["login"]}')
        else:
            messages.success(request, f'Successfully updated GitHub connection for {user_data["login"]}')
        
        return redirect('github:admin')
        
    except Exception as e:
        messages.error(request, f'Error during OAuth callback: {str(e)}')
        return redirect('github:admin')


@login_required
def disconnect(request):
    """Disconnect GitHub account"""
    try:
        token = GitHubToken.objects.filter(user=request.user).first()
        if token:
            token.delete()
            messages.success(request, 'GitHub account disconnected successfully')
        else:
            messages.info(request, 'No GitHub account connected')
        
        return redirect('users:dashboard')
        
    except Exception as e:
        messages.error(request, f'Error disconnecting GitHub account: {str(e)}')
        return redirect('users:dashboard')


@login_required
def admin_view(request):
    """Admin view for GitHub App configuration"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Superuser required.')
        return redirect('users:dashboard')
    
    try:
        github_app = GitHubApp.objects.first()
        
        if request.method == 'POST':
            form = GitHubAppForm(request.POST, instance=github_app)
            if form.is_valid():
                form.save()
                messages.success(request, 'GitHub App configuration saved successfully!')
                return redirect('github:admin')
        else:
            form = GitHubAppForm(instance=github_app)
        
        context = {
            'form': form,
            'github_app': github_app,
            'redirect_url': request.build_absolute_uri(reverse('github:callback')),
            'github_token': GitHubToken.objects.filter(user=request.user).first() if request.user.is_authenticated else None,
        }
        return render(request, 'github/admin.html', context)
        
    except Exception as e:
        messages.error(request, f'Error in admin view: {str(e)}')
        return render(request, 'github/admin.html', {'error': str(e)})
