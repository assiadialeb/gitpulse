from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm, CustomAuthenticationForm, UserProfileForm
from .models import UserProfile
from .services import GitHubUserService
# from models import GitHubUser  # Supprimé car inutilisé et cause une erreur linter
from analytics.models import Commit, PullRequest, DeveloperAlias, Developer  # mongoengine
import applications.models  # pour accès Django ORM
from django.utils import timezone
from collections import defaultdict


def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome, {user.username}!')
                return redirect('users:dashboard')
            else:
                # Add error to form instead of using messages
                form.add_error(None, 'Invalid username or password.')
        # Remove the else block that was adding messages.error
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'users/login.html', {'form': form})


def register_view(request):
    """Registration view"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {user.username}!')
            return redirect('users:dashboard')
        # Remove the else block that was adding messages.error
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'users/register.html', {'form': form})


@login_required
def logout_view(request):
    """Logout view"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('users:login')


@login_required
def profile_view(request):
    """User profile view with GitHub data sync"""
    github_user = None
    sync_error = None
    github_organizations = None
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user.userprofile)
        if form.is_valid():
            profile = form.save()
            
            # If GitHub username was provided, sync data
            if profile.github_username:
                try:
                    # Check if user has GitHub token
                    github_service = GitHubUserService(request.user.id)
                    
                    # Sync user data from GitHub
                    github_user = github_service.sync_user_data(profile.github_username)
                    
                    # Récupérer les organisations si superuser
                    if request.user.is_superuser:
                        try:
                            github_organizations = github_service.get_authenticated_user_organizations()
                        except Exception:
                            github_organizations = None
                    messages.success(request, f'Profile updated and GitHub data synced for {profile.github_username}!')
                    
                except ValueError as e:
                    sync_error = str(e)
                    messages.warning(request, f'Profile updated but GitHub sync failed: {sync_error}')
                    
                except Exception as e:
                    sync_error = str(e)
                    messages.error(request, f'Error syncing GitHub data: {sync_error}')
            
            else:
                messages.success(request, 'Profile updated successfully!')
            
            return redirect('users:profile')
    else:
        form = UserProfileForm(instance=request.user.userprofile)
        
        # Try to get existing GitHub user data
        if request.user.userprofile.github_username:
            try:
                # This .objects access works for both mongoengine and Django ORM
                github_user = User.objects.filter(username=request.user.userprofile.github_username).first()
            except Exception:
                pass
        # Récupérer les organisations si superuser
        if request.user.is_superuser:
            try:
                github_service = GitHubUserService(request.user.id)
                github_organizations = github_service.get_authenticated_user_organizations()
            except Exception:
                github_organizations = None
    
    context = {
        'form': form,
        'github_user': github_user,
        'sync_error': sync_error,
        'github_organizations': github_organizations
    }
    
    return render(request, 'users/profile.html', context)


def home_view(request):
    """Home view - redirects to login if not authenticated"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    return redirect('users:login')


@login_required
def dashboard_view(request):
    """Dashboard view"""
    total_repositories = applications.models.ApplicationRepository.objects.count()  # Django ORM
    total_commits = Commit.objects.count()  # mongoengine
    total_pull_requests = PullRequest.objects.count()  # mongoengine

    # Commits du mois (30 derniers jours)
    cutoff_date = timezone.now() - timezone.timedelta(days=30)
    recent_commits = Commit.objects.filter(authored_date__gte=cutoff_date)

    # Top développeurs (par Developer global, nom principal)
    dev_stats = defaultdict(int)
    alias_to_developer = {}
    # Préparer un mapping email -> Developer
    for alias in DeveloperAlias.objects.filter(developer__ne=None):
        alias_to_developer[alias.email.lower()] = alias.developer
    for commit in recent_commits:
        dev = alias_to_developer.get(commit.author_email.lower())
        if dev:
            key = dev.primary_name.strip()
        else:
            key = commit.author_name.strip()
        dev_stats[key] += 1
    top_developers = [{'name': name, 'commits': count} for name, count in sorted(dev_stats.items(), key=lambda x: -x[1])[:5]]

    # Top repositories (par nom)
    repo_stats = defaultdict(int)
    for commit in recent_commits:
        key = commit.repository_full_name.strip()
        repo_stats[key] += 1
    top_repositories = [{'repo': repo, 'commits': count} for repo, count in sorted(repo_stats.items(), key=lambda x: -x[1])[:5]]

    context = {
        'total_repositories': total_repositories,
        'total_commits': total_commits,
        'total_pull_requests': total_pull_requests,
        'top_developers': top_developers,
        'top_repositories': top_repositories,
    }
    return render(request, 'users/dashboard.html', context)
