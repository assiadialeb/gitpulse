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
from models import GitHubUser


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
                github_user = GitHubUser.objects(login=request.user.userprofile.github_username).first()
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
    return render(request, 'users/dashboard.html')
