from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
import requests
from .models import Application, ApplicationRepository
from .forms import ApplicationForm, RepositorySelectionForm
from github.models import GitHubToken


@login_required
def application_list(request):
    """List all applications for the current user"""
    applications = Application.objects.filter(owner=request.user)
    return render(request, 'applications/list.html', {
        'applications': applications
    })


@login_required
def application_create(request):
    """Create a new application"""
    if request.method == 'POST':
        form = ApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.owner = request.user
            application.save()
            messages.success(request, f'Application "{application.name}" created successfully!')
            return redirect('applications:detail', pk=application.pk)
    else:
        form = ApplicationForm()
    
    return render(request, 'applications/create.html', {
        'form': form
    })


@login_required
def application_detail(request, pk):
    """Display application details and repositories with analytics dashboard"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    repositories = application.repositories.all()
    
    # Get analytics data
    try:
        from analytics.analytics_service import AnalyticsService
        analytics = AnalyticsService(pk)
        
        context = {
            'application': application,
            'repositories': repositories,
            'overall_stats': analytics.get_overall_stats(),
            'developer_activity': analytics.get_developer_activity(days=30),
            'activity_heatmap': analytics.get_activity_heatmap(days=90),
            'bubble_chart': analytics.get_bubble_chart_data(days=30),
            'code_distribution': analytics.get_code_distribution(),
            'commit_quality': analytics.get_commit_quality_metrics(),
        }
    except ImportError:
        # If analytics app is not available, provide empty data
        context = {
            'application': application,
            'repositories': repositories,
            'overall_stats': {'total_commits': 0, 'total_authors': 0, 'total_additions': 0, 'total_deletions': 0},
            'developer_activity': {'developers': []},
            'activity_heatmap': {'daily_activity': []},
            'bubble_chart': {'bubbles': [], 'max_commits': 0},
            'code_distribution': {'distribution': []},
            'commit_quality': {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0},
        }
    except Exception as e:
        # If analytics service fails, provide empty data
        context = {
            'application': application,
            'repositories': repositories,
            'overall_stats': {'total_commits': 0, 'total_authors': 0, 'total_additions': 0, 'total_deletions': 0},
            'developer_activity': {'developers': []},
            'activity_heatmap': {'daily_activity': []},
            'bubble_chart': {'bubbles': [], 'max_commits': 0},
            'code_distribution': {'distribution': []},
            'commit_quality': {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0},
        }
    
    return render(request, 'applications/detail.html', context)


@login_required
def application_edit(request, pk):
    """Edit an existing application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    if request.method == 'POST':
        form = ApplicationForm(request.POST, instance=application)
        if form.is_valid():
            form.save()
            messages.success(request, f'Application "{application.name}" updated successfully!')
            return redirect('applications:detail', pk=application.pk)
    else:
        form = ApplicationForm(instance=application)
    
    return render(request, 'applications/edit.html', {
        'form': form,
        'application': application
    })


@login_required
def application_delete(request, pk):
    """Delete an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    if request.method == 'POST':
        application_name = application.name
        application_id = application.id
        
        # Clean up MongoDB data before deleting the application
        try:
            from analytics.services import cleanup_application_data
            cleanup_results = cleanup_application_data(application_id)
            
            if 'error' in cleanup_results:
                messages.warning(request, f'Application deleted but some data cleanup failed: {cleanup_results["error"]}')
            else:
                messages.success(request, f'Application "{application_name}" and all related data deleted successfully!')
                if cleanup_results['total_deleted'] > 0:
                    messages.info(request, f'Cleaned up {cleanup_results["total_deleted"]} MongoDB records.')
        except ImportError:
            # If analytics app is not available, just delete the application
            messages.success(request, f'Application "{application_name}" deleted successfully!')
        except Exception as e:
            # If cleanup fails, still delete the application but warn the user
            messages.warning(request, f'Application deleted but data cleanup failed: {str(e)}')
        
        # Delete the application
        application.delete()
        return redirect('applications:list')
    
    return render(request, 'applications/delete.html', {
        'application': application
    })


@login_required
def add_repositories(request, pk):
    """Add GitHub repositories to an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    # Get user's GitHub token
    try:
        github_token = GitHubToken.objects.get(user=request.user)
    except GitHubToken.DoesNotExist:
        messages.error(request, 'Please connect your GitHub account first.')
        return redirect('github:admin')
    
    # Fetch user's repositories from GitHub
    github_repos = []
    existing_repos = list(application.repositories.values_list('github_repo_name', flat=True))
    print(f"Debug: Found {len(existing_repos)} existing repos: {existing_repos}")
    
    try:
        headers = {
            'Authorization': f'token {github_token.access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get user's repositories (both owned and collaborated) - get more pages
        all_repos = []
        page = 1
        while True:
            response = requests.get('https://api.github.com/user/repos', headers=headers, params={
                'sort': 'updated',
                'per_page': 100,
                'type': 'all',  # Include all repos (owned, collaborated, etc.)
                'page': page
            })
            
            print(f"GitHub API Response Status: {response.status_code}")
            print(f"GitHub API Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                repos_page = response.json()
                if not repos_page:  # No more repos
                    break
                all_repos.extend(repos_page)
                print(f"Page {page}: Found {len(repos_page)} repositories")
                page += 1
                if page > 10:  # Limit to 1000 repos max
                    break
            else:
                print(f"GitHub API Error: {response.status_code} - {response.text}")
                messages.error(request, f'Failed to fetch repositories from GitHub. Status: {response.status_code}')
                return redirect('applications:detail', pk=pk)
        
        github_repos = all_repos
        print(f"Total repositories found: {len(github_repos)}")
        for repo in github_repos[:3]:  # Show first 3 repos for debug
            print(f"  - {repo.get('full_name', 'N/A')}: {repo.get('description', 'No description')}")
            
    except Exception as e:
        messages.error(request, f'Error connecting to GitHub: {str(e)}')
        return redirect('applications:detail', pk=pk)
    
    if request.method == 'POST':
        # Check if this is a search request
        if 'search' in request.POST:
            # Just re-render with search results
            form = RepositorySelectionForm(
                request.POST,
                github_repos=github_repos,
                existing_repos=existing_repos,
                search_query=request.POST.get('search_query', '')
            )
            choices = form.fields['repositories'].choices
            return render(request, 'applications/add_repositories.html', {
                'form': form,
                'application': application,
                'github_repos': github_repos,
                'existing_repos': existing_repos,
                'choices_count': len(choices),
                'choices': choices  # Passer les choix directement
            })
        
        # This is a form submission to add repositories
        form = RepositorySelectionForm(
            request.POST,
            github_repos=github_repos,
            existing_repos=existing_repos,
            search_query=request.POST.get('search_query', '')
        )
        
        if form.is_valid():
            selected_repos = form.cleaned_data['repositories']
            added_count = 0
            
            for repo_name in selected_repos:
                # Find the repo data in github_repos
                repo_data = next((repo for repo in github_repos if repo['full_name'] == repo_name), None)
                
                if repo_data:
                    ApplicationRepository.objects.create(
                        application=application,
                        github_repo_name=repo_data['full_name'],
                        github_repo_id=repo_data['id'],
                        github_repo_url=repo_data.get('clone_url', ''),
                        description=repo_data.get('description', ''),
                        default_branch=repo_data.get('default_branch', 'main'),
                        is_private=repo_data.get('private', False),
                        language=repo_data.get('language', ''),
                        stars_count=repo_data.get('stargazers_count', 0),
                        forks_count=repo_data.get('forks_count', 0),
                        last_updated=repo_data.get('pushed_at')
                    )
                    added_count += 1
            
            if added_count > 0:
                messages.success(request, f'Added {added_count} repositories to "{application.name}".')
            else:
                messages.info(request, 'No repositories were added.')
            
            return redirect('applications:detail', pk=pk)
    else:
        form = RepositorySelectionForm(
            github_repos=github_repos,
            existing_repos=existing_repos,
            search_query=''  # Toujours vide en GET pour afficher tous les repos
        )
    
    # Debug: vérifier que le formulaire a bien les choix
    print(f"DEBUG VIEW: Form choices count: {len(form.fields['repositories'].choices)}")
    print(f"DEBUG VIEW: First 3 choices: {form.fields['repositories'].choices[:3]}")
    
    # Passer les choix directement au template
    choices = form.fields['repositories'].choices
    
    return render(request, 'applications/add_repositories.html', {
        'form': form,
        'application': application,
        'github_repos': github_repos,
        'existing_repos': existing_repos,
        'choices_count': len(choices),
        'choices': choices  # Passer les choix directement
    })


@login_required
def remove_repository(request, pk, repo_id):
    """Remove a repository from an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    repository = get_object_or_404(ApplicationRepository, pk=repo_id, application=application)
    
    if request.method == 'POST':
        repo_name = repository.github_repo_name
        repository.delete()
        messages.success(request, f'Repository "{repo_name}" removed from "{application.name}".')
    
    return redirect('applications:detail', pk=pk)


@login_required
def debug_github(request):
    """Debug GitHub connection and repositories"""
    try:
        github_token = GitHubToken.objects.get(user=request.user)
        print(f"Found GitHub token for user {request.user.username}")
        print(f"Token: {github_token.access_token[:10]}...")
        
        headers = {
            'Authorization': f'token {github_token.access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Test user info
        user_response = requests.get('https://api.github.com/user', headers=headers)
        print(f"User API Status: {user_response.status_code}")
        if user_response.status_code == 200:
            user_data = user_response.json()
            print(f"GitHub User: {user_data.get('login', 'N/A')}")
        
        # Test repositories
        repos_response = requests.get('https://api.github.com/user/repos', headers=headers, params={
            'sort': 'updated',
            'per_page': 10
        })
        print(f"Repos API Status: {repos_response.status_code}")
        if repos_response.status_code == 200:
            repos_data = repos_response.json()
            print(f"Found {len(repos_data)} repositories")
            for repo in repos_data:
                print(f"  - {repo.get('full_name', 'N/A')}")
        
        return render(request, 'applications/debug_github.html', {
            'github_token': github_token,
            'user_response': user_response,
            'repos_response': repos_response
        })
        
    except GitHubToken.DoesNotExist:
        messages.error(request, 'No GitHub token found. Please connect your GitHub account.')
        return redirect('github:admin')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
        return redirect('applications:list')
