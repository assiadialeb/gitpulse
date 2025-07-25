import json
import requests
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.exceptions import PermissionDenied
import re

from .models import Application, ApplicationRepository
from .forms import ApplicationForm, RepositorySelectionForm
from analytics.github_token_service import GitHubTokenService
from analytics.cache_service import AnalyticsCacheService





@login_required
def application_list(request):
    """List all applications for all users"""
    applications = Application.objects.all()
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
    
    # Get repositories for this application
    repositories = application.repositories.all()
    
    # Get analytics data with caching
    try:
        from analytics.analytics_service import AnalyticsService
        from analytics.cache_service import AnalyticsCacheService
        analytics = AnalyticsService(pk)
        
        # Try to get all metrics from cache first
        overall_stats = AnalyticsCacheService.get_overall_stats(application.id)
        developer_activity = AnalyticsCacheService.get_developer_activity(application.id, days=30)
        developer_activity_120d = AnalyticsCacheService.get_developer_activity(application.id, days=120)
        commit_frequency = AnalyticsCacheService.get_commit_frequency(application.id)
        release_frequency = AnalyticsCacheService.get_release_frequency(application.id, period_days=30)
        total_releases = AnalyticsCacheService.get_total_releases(application.id)
        pr_cycle_times = AnalyticsCacheService.get_pr_cycle_times(application.id)
        code_distribution = AnalyticsCacheService.get_code_distribution(application.id)
        activity_heatmap = AnalyticsCacheService.get_activity_heatmap(application.id, days=90)
        bubble_chart = AnalyticsCacheService.get_bubble_chart(application.id, days=30)
        commit_quality = AnalyticsCacheService.get_commit_quality(application.id)
        commit_types = AnalyticsCacheService.get_commit_types(application.id)
        application_quality_metrics = AnalyticsCacheService.get_quality_metrics(application.id)
        
        # Check if we have cached data for this application
        cached_data = AnalyticsCacheService.get_overall_stats(application.id)
        
        if cached_data is not None:
            print(f"Using cached metrics for app {application.id}")
            # Use cached data
            overall_stats = cached_data
            developer_activity = AnalyticsCacheService.get_developer_activity(application.id, days=30)
            developer_activity_120d = AnalyticsCacheService.get_developer_activity(application.id, days=120)
            commit_frequency = AnalyticsCacheService.get_commit_frequency(application.id)
            release_frequency = AnalyticsCacheService.get_release_frequency(application.id, period_days=30)
            total_releases = AnalyticsCacheService.get_total_releases(application.id)
            pr_cycle_times = AnalyticsCacheService.get_pr_cycle_times(application.id)
            code_distribution = AnalyticsCacheService.get_code_distribution(application.id)
            activity_heatmap = AnalyticsCacheService.get_activity_heatmap(application.id, days=90)
            bubble_chart = AnalyticsCacheService.get_bubble_chart(application.id, days=30)
            commit_quality = AnalyticsCacheService.get_commit_quality(application.id)
            commit_types = AnalyticsCacheService.get_commit_types(application.id)
            application_quality_metrics = AnalyticsCacheService.get_quality_metrics(application.id)
        else:
            print(f"Calculating metrics for app {application.id} (not in cache)")
            
            # Calculate all metrics
            overall_stats = analytics.get_overall_stats()
            developer_activity = analytics.get_developer_activity(days=30)
            developer_activity_120d = analytics.get_developer_activity(days=120)
            
            try:
                commit_frequency = analytics.get_application_commit_frequency()
            except Exception as e:
                print(f"Error getting commit frequency: {e}")
                commit_frequency = {
                    'avg_commits_per_day': 0, 'recent_activity_score': 0, 'consistency_score': 0,
                    'overall_frequency_score': 0, 'commits_last_30_days': 0, 'commits_last_90_days': 0,
                    'days_since_last_commit': None, 'active_days': 0, 'total_days': 0
                }
            
            try:
                release_frequency = analytics.get_release_frequency(period_days=30)
            except Exception as e:
                print(f"Error getting release frequency: {e}")
                release_frequency = {
                    'releases_per_month': 0, 'releases_per_week': 0, 'total_releases': 0, 'period_days': 30
                }
            
            try:
                total_releases = analytics.get_total_releases()
            except Exception as e:
                print(f"Error getting total releases: {e}")
                total_releases = 0
            
            pr_cycle_times = analytics.get_pr_cycle_times()
            code_distribution = analytics.get_code_distribution()
            activity_heatmap = analytics.get_activity_heatmap(days=90)
            bubble_chart = analytics.get_bubble_chart_data(days=30)
            commit_quality = analytics.get_commit_quality_metrics()
            commit_types = analytics.get_commit_type_distribution()
            application_quality_metrics = _generate_application_quality_metrics(application)
            
            # Cache all metrics
            AnalyticsCacheService.set_overall_stats(application.id, overall_stats)
            AnalyticsCacheService.set_developer_activity(application.id, developer_activity, days=30)
            AnalyticsCacheService.set_developer_activity(application.id, developer_activity_120d, days=120)
            AnalyticsCacheService.set_commit_frequency(application.id, commit_frequency)
            AnalyticsCacheService.set_release_frequency(application.id, release_frequency, period_days=30)
            AnalyticsCacheService.set_total_releases(application.id, total_releases)
            AnalyticsCacheService.set_pr_cycle_times(application.id, pr_cycle_times)
            AnalyticsCacheService.set_code_distribution(application.id, code_distribution)
            AnalyticsCacheService.set_activity_heatmap(application.id, activity_heatmap, days=90)
            AnalyticsCacheService.set_bubble_chart(application.id, bubble_chart, days=30)
            AnalyticsCacheService.set_commit_quality(application.id, commit_quality)
            AnalyticsCacheService.set_commit_types(application.id, commit_types)
            AnalyticsCacheService.set_quality_metrics(application.id, application_quality_metrics)
        
        # Calculate derived metrics
        active_developers_count_120d = len(developer_activity_120d.get('developers', []))
        
        # Calculate PR cycle time statistics
        pr_times = [pr['cycle_time_hours'] for pr in pr_cycle_times if pr['cycle_time_hours'] is not None]
        pr_cycle_time_median = None
        pr_cycle_time_min = None
        pr_cycle_time_max = None
        if pr_times:
            pr_times_sorted = sorted(pr_times)
            n = len(pr_times_sorted)
            pr_cycle_time_min = pr_times_sorted[0]
            pr_cycle_time_max = pr_times_sorted[-1]
            if n % 2 == 1:
                pr_cycle_time_median = pr_times_sorted[n // 2]
            else:
                pr_cycle_time_median = (pr_times_sorted[n // 2 - 1] + pr_times_sorted[n // 2]) / 2
        pr_cycle_time_count = len(pr_times)
        
        # PR health metrics will be loaded asynchronously via JavaScript
        pr_health_metrics = {
            'total_prs': 0, 'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0,
            'prs_without_review': 0, 'prs_without_review_rate': 0, 'self_merged_prs': 0,
            'self_merged_rate': 0, 'old_open_prs': 0, 'old_open_prs_rate': 0,
            'avg_merge_time_hours': 0, 'median_merge_time_hours': 0
        }
        
        context = {
            'application': application,
            'repositories': repositories,
            'overall_stats': overall_stats,
            'developer_activity': developer_activity,
            # Ajout du nombre d'active developers sur 120 jours
            'active_developers_count_120d': active_developers_count_120d,
            'activity_heatmap': analytics.get_activity_heatmap(days=90),
            'bubble_chart': analytics.get_bubble_chart_data(days=30),
            'code_distribution': analytics.get_code_distribution(),
            'commit_quality': analytics.get_commit_quality_metrics(),
            'commit_types': analytics.get_commit_type_distribution(),
            'commit_frequency': commit_frequency,
            'release_frequency': release_frequency,
            'application_quality_metrics': application_quality_metrics,
            'pr_health_metrics': pr_health_metrics,
            'pr_cycle_times': pr_cycle_times,
            'pr_cycle_time_median': pr_cycle_time_median,
            'pr_cycle_time_min': pr_cycle_time_min,
            'pr_cycle_time_max': pr_cycle_time_max,
            'pr_cycle_time_count': pr_cycle_time_count,
            'total_releases': total_releases,  # Ajout pour le template
        }
        doughnut_colors = {
            'fix': '#4caf50',
            'feature': '#2196f3',
            'docs': '#ffeb3b',
            'refactor': '#ff9800',
            'test': '#9c27b0',
            'style': '#00bcd4',
            'chore': '#607d8b',
            'other': '#bdbdbd',
        }
        context['doughnut_colors'] = doughnut_colors
        # Robust preparation for JS variables
        commit_types = context.get('commit_types') or {}
        counts = commit_types.get('counts') if isinstance(commit_types, dict) else None
        if counts and isinstance(counts, dict):
            labels = list(counts.keys())
            values = list(counts.values())
        else:
            labels = []
            values = []
        context['commit_type_labels'] = json.dumps(labels)
        context['commit_type_values'] = json.dumps(values)
        legend_data = []
        for label, count in (counts.items() if counts else []):
            color = context['doughnut_colors'].get(label, '#bdbdbd')
            legend_data.append({'label': label, 'count': count, 'color': color})
        context['commit_type_legend'] = legend_data
        # Robust JS variables for charts
        bubble_chart = context.get('bubble_chart') or {}
        context['bubble_chart_data'] = json.dumps(bubble_chart.get('datasets', []))
        activity_heatmap = context.get('activity_heatmap') or {}
        context['activity_heatmap_data'] = json.dumps(activity_heatmap.get('daily_activity', []))
        context['debug_stats'] = overall_stats
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
            'commit_types': {'counts': {}},
            'commit_frequency': {'avg_commits_per_day': 0, 'recent_activity_score': 0, 'consistency_score': 0, 'overall_frequency_score': 0, 'commits_last_30_days': 0, 'commits_last_90_days': 0, 'days_since_last_commit': None, 'active_days': 0, 'total_days': 0},
            'application_quality_metrics': {'total_commits': 0, 'real_code_commits': 0, 'real_code_ratio': 0, 'suspicious_commits': 0, 'suspicious_ratio': 0, 'doc_only_commits': 0, 'doc_only_ratio': 0, 'config_only_commits': 0, 'config_only_ratio': 0, 'micro_commits': 0, 'micro_commits_ratio': 0, 'no_ticket_commits': 0, 'no_ticket_ratio': 0, 'avg_code_quality': 0, 'avg_impact': 0, 'avg_complexity': 0},
            'pr_health_metrics': {'total_prs': 0, 'open_prs': 0, 'open_prs_percentage': 0, 'merged_prs': 0, 'merged_prs_percentage': 0, 'closed_prs': 0, 'prs_without_review': 0, 'prs_without_review_rate': 0, 'self_merged_prs': 0, 'self_merged_rate': 0, 'old_open_prs': 0, 'old_open_prs_rate': 0, 'avg_merge_time_hours': 0, 'median_merge_time_hours': 0},
        }
        # Robust JS variables for charts (even in import error case)
        context['commit_type_labels'] = json.dumps([])
        context['commit_type_values'] = json.dumps([])
        context['bubble_chart_data'] = json.dumps([])
        context['activity_heatmap_data'] = json.dumps([])
        context['commit_type_legend'] = []
        context['debug_stats'] = context['overall_stats']
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
            'commit_types': {'counts': {}},
            'commit_frequency': {'avg_commits_per_day': 0, 'recent_activity_score': 0, 'consistency_score': 0, 'overall_frequency_score': 0, 'commits_last_30_days': 0, 'commits_last_90_days': 0, 'days_since_last_commit': None, 'active_days': 0, 'total_days': 0},
            'application_quality_metrics': {'total_commits': 0, 'real_code_commits': 0, 'real_code_ratio': 0, 'suspicious_commits': 0, 'suspicious_ratio': 0, 'doc_only_commits': 0, 'doc_only_ratio': 0, 'config_only_commits': 0, 'config_only_ratio': 0, 'micro_commits': 0, 'micro_commits_ratio': 0, 'no_ticket_commits': 0, 'no_ticket_ratio': 0, 'avg_code_quality': 0, 'avg_impact': 0, 'avg_complexity': 0},
            'pr_health_metrics': {'total_prs': 0, 'open_prs': 0, 'open_prs_percentage': 0, 'merged_prs': 0, 'merged_prs_percentage': 0, 'closed_prs': 0, 'prs_without_review': 0, 'prs_without_review_rate': 0, 'self_merged_prs': 0, 'self_merged_rate': 0, 'old_open_prs': 0, 'old_open_prs_rate': 0, 'avg_merge_time_hours': 0, 'median_merge_time_hours': 0},
        }
        # Robust JS variables for charts (even in error case)
        context['commit_type_labels'] = json.dumps([])
        context['commit_type_values'] = json.dumps([])
        context['bubble_chart_data'] = json.dumps([])
        context['activity_heatmap_data'] = json.dumps([])
        context['commit_type_legend'] = []
        context['debug_stats'] = context['overall_stats']
    
    return render(request, 'applications/detail.html', context)


@login_required
def application_edit(request, pk):
    """Edit an application"""
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
        name = application.name
        application.delete()
        messages.success(request, f'Application "{name}" deleted successfully!')
        return redirect('applications:list')
    
    return render(request, 'applications/delete.html', {
        'application': application
    })


@login_required
def remove_repository(request, pk, repo_id):
    """Remove a repository from an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    repository = get_object_or_404(ApplicationRepository, pk=repo_id, application=application)
    
    if request.method == 'POST':
        repo_name = repository.github_repo_name
        repository.delete()
        messages.success(request, f'Repository "{repo_name}" removed from "{application.name}"')
        return redirect('applications:detail', pk=application.pk)
    
    return render(request, 'applications/remove_repository.html', {
        'application': application,
        'repository': repository
    })


@login_required
def add_repositories(request, pk):
    """Add GitHub repositories to an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    # Get user's GitHub token for repository access
    github_token = GitHubTokenService.get_token_for_operation('private_repos', request.user.id)
    print(f"DEBUG: Token found via service: {bool(github_token)}")
    
    # If no token via service, try to get it from session or other sources
    if not github_token:
        # Try to get token from session (for GitHub SSO)
        github_token = request.session.get('github_token')
        print(f"DEBUG: Token from session: {bool(github_token)}")
        
        # If still no token, try to get it from the user's social account
        if not github_token:
            try:
                from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp
                social_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
                if social_account:
                    app = SocialApp.objects.filter(provider='github').first()
                    if app:
                        social_token = SocialToken.objects.filter(account=social_account, app=app).first()
                        if social_token:
                            github_token = social_token.token
                            print(f"DEBUG: Token from SocialToken: {bool(github_token)}")
            except Exception as e:
                print(f"DEBUG: Error getting token from SocialToken: {e}")
        
        # If still no token, try to get it from the social account's extra data
        if not github_token:
            try:
                from allauth.socialaccount.models import SocialAccount
                social_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
                if social_account and social_account.extra_data:
                    # Try to get access_token from extra_data
                    github_token = social_account.extra_data.get('access_token')
                    print(f"DEBUG: Token from extra_data: {bool(github_token)}")
            except Exception as e:
                print(f"DEBUG: Error getting token from extra_data: {e}")
        
        # If still no token, try to use the OAuth App token for basic operations
        if not github_token:
            try:
                from allauth.socialaccount.models import SocialApp
                app = SocialApp.objects.filter(provider='github').first()
                if app and app.secret:
                    github_token = app.secret
                    print(f"DEBUG: Using OAuth App token as fallback: {bool(github_token)}")
            except Exception as e:
                print(f"DEBUG: Error getting OAuth App token: {e}")
        
        # If still no token, redirect to GitHub connection
        if not github_token:
            messages.error(request, 'Please connect your GitHub account first.')
            return redirect('socialaccount_connections')
        
        # If we have a token but it's a test token, redirect to GitHub to get a real one
        if github_token and github_token.startswith('ghp_test_'):
            messages.warning(request, 'Please reconnect via GitHub to get a valid token.')
            return redirect('socialaccount_connections')
    
    # Get existing repos for this application
    existing_repos = list(application.repositories.values_list('github_repo_name', flat=True))
    print(f"Debug: Found {len(existing_repos)} existing repos: {existing_repos}")
    
    # For GET requests, just render the template - JavaScript will handle the API calls
    if request.method == 'GET':
        return render(request, 'applications/add_repositories.html', {
            'application': application,
            'existing_repos': existing_repos,
        })
    
    # For POST requests, handle repository addition
    if request.method == 'POST':
        selected_repos = request.POST.getlist('repositories')
        added_count = 0
        
        if selected_repos:
            try:
                from analytics.github_service import GitHubService
                github_service = GitHubService(github_token)
                
                for repo_name in selected_repos:
                    # Get repo details from GitHub API
                    repo_data, _ = github_service._make_request(f'https://api.github.com/repos/{repo_name}')
                    
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
                    
            except Exception as e:
                messages.error(request, f'Error adding repositories: {str(e)}')
        
        return redirect('applications:detail', pk=pk)


@login_required
@require_http_methods(["GET"])
def api_get_repositories(request, pk):
    """API endpoint to get GitHub repositories with caching and real-time search"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    # Get user's GitHub token for repository access
    github_token = GitHubTokenService.get_token_for_operation('private_repos', request.user.id)
    if not github_token:
        return JsonResponse({'error': 'GitHub token not found'}, status=401)
    
    # Get search query
    search_query = request.GET.get('search', '').lower()
    
    # Get existing repos for this application
    existing_repos = list(application.repositories.values_list('github_repo_name', flat=True))
    
    try:
        from analytics.github_service import GitHubService
        github_service = GitHubService(github_token)
        
        # Get user's repositories
        all_repos = []
        page = 1
        while True:
            url = 'https://api.github.com/user/repos'
            params = {
                'sort': 'updated',
                'per_page': 100,
                'type': 'all',
                'page': page
            }
            
            repos_data, _ = github_service._make_request(url, params)
            
            if repos_data is not None:
                if not repos_data:
                    break
                all_repos.extend(repos_data)
                page += 1
                if page > 10:
                    break
            else:
                return JsonResponse({'error': 'GitHub API error'}, status=500)
        
        # Filter repositories
        filtered_repos = []
        for repo in all_repos:
            repo_name = repo.get('full_name', '')
            description = repo.get('description', '')
            
            # Skip if already added
            if repo_name in existing_repos:
                continue
            
            # Filter by search query if provided
            if search_query:
                if (search_query not in repo_name.lower() and 
                    search_query not in (description or '').lower()):
                    continue
            
            filtered_repos.append({
                'full_name': repo_name,
                'description': description or 'No description',
                'is_private': repo.get('private', False),
                'language': repo.get('language', ''),
                'stars_count': repo.get('stargazers_count', 0),
                'forks_count': repo.get('forks_count', 0),
                'updated_at': repo.get('pushed_at')
            })
        
        return JsonResponse({
            'repositories': filtered_repos,
            'total_count': len(filtered_repos),
            'search_query': search_query
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Error fetching repositories: {str(e)}'}, status=500)


@login_required
def debug_github(request):
    """Debug GitHub connection and token access"""
    try:
        # Test different token types
        basic_token = GitHubTokenService.get_token_for_operation('basic')
        user_token = GitHubTokenService.get_token_for_operation('private_repos', request.user.id)
        
        # Validate tokens
        basic_validation = GitHubTokenService.validate_token_access(basic_token) if basic_token else None
        user_validation = GitHubTokenService.validate_token_access(user_token) if user_token else None
        
        context = {
            'basic_token': basic_token,
            'user_token': user_token,
            'basic_validation': basic_validation,
            'user_validation': user_validation,
        }
        
        return render(request, 'applications/debug_github.html', context)
        
    except Exception as e:
        messages.error(request, f'Error debugging GitHub: {str(e)}')
        return redirect('applications:list')




def _calculate_application_code_quality_score(app_id):
    """
    Calculate code quality score for an application based on the same rules as developers
    """
    try:
        from analytics.models import Commit
        import re
        
        commits = Commit.objects(application_id=app_id)
        if commits.count() == 0:
            return 0.0
        
        quality_scores = []
        
        for commit in commits:
            # Base score
            code_quality = 50
            
            # Check for real code files
            has_code_files = False
            for file_change in commit.files_changed:
                filename = file_change.filename.lower()
                
                # Check for code files
                if any(ext in filename for ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.rb']):
                    has_code_files = True
                    break
                
                # Check for test files
                elif any(pattern in filename for pattern in ['test', 'spec', 'specs', '_test.', '.test.']):
                    has_code_files = True
                    break
            
            # Add points for code files
            if has_code_files:
                code_quality += 40
            
            # Add points for substantial changes
            if commit.total_changes > 10:
                code_quality += 15
            
            quality_scores.append(min(100, code_quality))
        
        return round(sum(quality_scores) / len(quality_scores), 1)
        
    except Exception as e:
        print(f"Error calculating application code quality score: {e}")
        return 0.0


def _calculate_application_impact_score(app_id):
    """
    Calculate impact score for an application based on the same rules as developers
    """
    try:
        from analytics.models import Commit
        
        commits = Commit.objects(application_id=app_id)
        if commits.count() == 0:
            return 0.0
        
        impact_scores = []
        
        for commit in commits:
            # Base score
            impact_score = 50
            
            # Add points based on changes
            if commit.total_changes > 20:
                impact_score += 40
            elif commit.total_changes > 10:
                impact_score += 30
            elif commit.total_changes > 5:
                impact_score += 20
            
            impact_scores.append(min(100, impact_score))
        
        return round(sum(impact_scores) / len(impact_scores), 1)
        
    except Exception as e:
        print(f"Error calculating application impact score: {e}")
        return 0.0


def _calculate_application_complexity_score(app_id):
    """
    Calculate complexity score for an application based on the same rules as developers
    """
    try:
        from analytics.models import Commit
        
        commits = Commit.objects(application_id=app_id)
        if commits.count() == 0:
            return 0.0
        
        complexity_scores = []
        
        for commit in commits:
            # Base score
            complexity_score = 30
            
            # Add points based on commit type
            if commit.commit_type == 'feature':
                complexity_score += 40
            elif commit.commit_type == 'fix':
                complexity_score += 35
            elif commit.commit_type == 'refactor':
                complexity_score += 30
            
            complexity_scores.append(min(100, complexity_score))
        
        return round(sum(complexity_scores) / len(complexity_scores), 1)
        
    except Exception as e:
        print(f"Error calculating application complexity score: {e}")
        return 0.0


def _generate_application_quality_metrics(application):
    """Generate application quality metrics using MongoDB aggregation"""
    try:
        from analytics.models import Commit
        from datetime import datetime, timedelta
        
        # Get all commits for this application
        commits = Commit.objects(application_id=application.id)
        
        if not commits:
            return {
                'total_commits': 0,
                'real_code_commits': 0,
                'real_code_ratio': 0,
                'suspicious_commits': 0,
                'suspicious_ratio': 0,
                'doc_only_commits': 0,
                'doc_only_ratio': 0,
                'config_only_commits': 0,
                'config_only_ratio': 0,
                'micro_commits': 0,
                'micro_commits_ratio': 0,
                'no_ticket_commits': 0,
                'no_ticket_ratio': 0,
                'avg_code_quality': 0,
                'avg_impact': 0,
                'avg_complexity': 0
            }
        
        # MongoDB aggregation pipeline for quality metrics
        pipeline = [
            {"$match": {"application_id": application.id}},
            {"$group": {
                "_id": None,
                "total_commits": {"$sum": 1},
                "real_code_commits": {"$sum": {"$cond": [{"$in": ["$commit_type", ["feat", "fix", "refactor", "perf"]]}, 1, 0]}},
                "suspicious_commits": {"$sum": {"$cond": [{"$in": ["$commit_type", ["revert", "hotfix"]]}, 1, 0]}},
                "doc_only_commits": {"$sum": {"$cond": [{"$eq": ["$commit_type", "docs"]}, 1, 0]}},
                "config_only_commits": {"$sum": {"$cond": [{"$in": ["$commit_type", ["chore", "ci", "build"]]}, 1, 0]}},
                "micro_commits": {"$sum": {"$cond": [{"$lte": ["$total_changes", 2]}, 1, 0]}},
                "no_ticket_commits": {"$sum": {"$cond": [{"$not": {"$regexMatch": {"input": "$message", "regex": "(?i)(fix|close|resolve|closes|closed|resolves|resolved|issue|ticket)"}}}, 1, 0]}},
                "avg_additions": {"$avg": "$additions"},
                "avg_deletions": {"$avg": "$deletions"},
                "avg_total_changes": {"$avg": "$total_changes"}
            }}
        ]
        
        result = list(commits.aggregate(pipeline))
        
        if not result:
            return {
                'total_commits': 0,
                'real_code_commits': 0,
                'real_code_ratio': 0,
                'suspicious_commits': 0,
                'suspicious_ratio': 0,
                'doc_only_commits': 0,
                'doc_only_ratio': 0,
                'config_only_commits': 0,
                'config_only_ratio': 0,
                'micro_commits': 0,
                'micro_commits_ratio': 0,
                'no_ticket_commits': 0,
                'no_ticket_ratio': 0,
                'avg_code_quality': 0,
                'avg_impact': 0,
                'avg_complexity': 0
            }
        
        metrics = result[0]
        total_commits = metrics['total_commits']
        
        return {
            'total_commits': total_commits,
            'real_code_commits': metrics['real_code_commits'],
            'real_code_ratio': round((metrics['real_code_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'suspicious_commits': metrics['suspicious_commits'],
            'suspicious_ratio': round((metrics['suspicious_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'doc_only_commits': metrics['doc_only_commits'],
            'doc_only_ratio': round((metrics['doc_only_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'config_only_commits': metrics['config_only_commits'],
            'config_only_ratio': round((metrics['config_only_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'micro_commits': metrics['micro_commits'],
            'micro_commits_ratio': round((metrics['micro_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'no_ticket_commits': metrics['no_ticket_commits'],
            'no_ticket_ratio': round((metrics['no_ticket_commits'] / total_commits * 100) if total_commits > 0 else 0, 1),
            'avg_code_quality': _calculate_application_code_quality_score(application.id),
            'avg_impact': _calculate_application_impact_score(application.id),
            'avg_complexity': _calculate_application_complexity_score(application.id)
        }
        
    except Exception as e:
        print(f"Error generating application quality metrics: {e}")
        return {
            'total_commits': 0,
            'real_code_commits': 0,
            'real_code_ratio': 0,
            'suspicious_commits': 0,
            'suspicious_ratio': 0,
            'doc_only_commits': 0,
            'doc_only_ratio': 0,
            'config_only_commits': 0,
            'config_only_ratio': 0,
            'micro_commits': 0,
            'micro_commits_ratio': 0,
            'no_ticket_commits': 0,
            'no_ticket_ratio': 0,
            'avg_code_quality': 0,
            'avg_impact': 0,
            'avg_complexity': 0
        }


def _generate_pr_health_metrics(application):
    """Generate Pull Request Health metrics using MongoDB aggregation"""
    try:
        from analytics.models import PullRequest
        from datetime import datetime, timedelta
        
        # Try to get from cache first
        cached_metrics = AnalyticsCacheService.get_pr_health_metrics(application.id)
        if cached_metrics is not None:
            return cached_metrics
        
        # Get all PRs for this application
        prs = PullRequest.objects(application_id=application.id)
        
        if not prs:
            return {
                'total_prs': 0,
                'open_prs': 0,
                'merged_prs': 0,
                'closed_prs': 0,
                'prs_without_review': 0,
                'prs_without_review_rate': 0,
                'self_merged_prs': 0,
                'self_merged_rate': 0,
                'old_open_prs': 0,
                'old_open_prs_rate': 0,
                'avg_merge_time_hours': 0,
                'median_merge_time_hours': 0
            }
        
        # Calculate cutoff date for old PRs (7 days)
        cutoff_date = datetime.now() - timedelta(days=7)
        
        # MongoDB aggregation pipeline for PR health metrics
        pipeline = [
            {"$match": {"application_id": application.id}},
            {"$group": {
                "_id": None,
                "total_prs": {"$sum": 1},
                "open_prs": {"$sum": {"$cond": [{"$eq": ["$state", "open"]}, 1, 0]}},
                "merged_prs": {"$sum": {"$cond": [{"$ne": ["$merged_at", None]}, 1, 0]}},
                "closed_prs": {"$sum": {"$cond": [{"$eq": ["$state", "closed"]}, 1, 0]}},
                # PRs that were open for more than 7 days before being closed
                "old_open_prs": {"$sum": {"$cond": [
                    {"$and": [
                        {"$eq": ["$state", "closed"]},
                        {"$ne": ["$created_at", None]},
                        {"$ne": ["$closed_at", None]},
                        {"$gte": [
                            {"$divide": [
                                {"$subtract": ["$closed_at", "$created_at"]},
                                1000 * 60 * 60 * 24  # Convert milliseconds to days
                            ]},
                            7
                        ]}
                    ]}, 1, 0]}}
            }}
        ]
        
        result = list(prs.aggregate(pipeline))
        
        if not result:
            return {
                'total_prs': 0,
                'open_prs': 0,
                'merged_prs': 0,
                'closed_prs': 0,
                'prs_without_review': 0,
                'prs_without_review_rate': 0,
                'self_merged_prs': 0,
                'self_merged_rate': 0,
                'old_open_prs': 0,
                'old_open_prs_rate': 0,
                'avg_merge_time_hours': 0,
                'median_merge_time_hours': 0
            }
        
        metrics = result[0]
        total_prs = metrics['total_prs']
        
        # Calculate merge times for median and average
        merge_times = []
        total_merge_time_seconds = 0
        merged_count = 0
        
        for pr in prs:
            if pr.merged_at and pr.created_at:
                merge_time_seconds = (pr.merged_at - pr.created_at).total_seconds()
                merge_time_hours = merge_time_seconds / 3600
                merge_times.append(merge_time_hours)
                total_merge_time_seconds += merge_time_seconds
                merged_count += 1
        
        # Calculate average merge time
        avg_merge_time_hours = (total_merge_time_seconds / merged_count / 3600) if merged_count > 0 else 0
        
        # Calculate median merge time
        median_merge_time = 0
        if merge_times:
            merge_times.sort()
            n = len(merge_times)
            if n % 2 == 1:
                median_merge_time = merge_times[n // 2]
            else:
                median_merge_time = (merge_times[n // 2 - 1] + merge_times[n // 2]) / 2
        
        # Detect self-merges using the new merged_by field
        self_merged_prs = 0
        for pr in prs:
            if pr.merged_at and pr.merged_by and pr.author:
                if pr.merged_by == pr.author:
                    self_merged_prs += 1
        
        # Estimate PRs without review (simplified logic)
        # This is an approximation since we don't have detailed review data
        # Consider self-merged PRs as potentially without proper review
        # Also include PRs with very few comments as potentially unreviewed
        prs_without_review = 0
        for pr in prs:
            if pr.merged_at:
                # Self-merged PRs are considered potentially unreviewed
                if pr.merged_by and pr.author and pr.merged_by == pr.author:
                    prs_without_review += 1
                # PRs with very few comments might also be unreviewed
                elif pr.comments_count <= 1:  # Only author's comment
                    prs_without_review += 1
        
        result_metrics = {
            'total_prs': total_prs,
            'open_prs': metrics['open_prs'],
            'open_prs_percentage': round((metrics['open_prs'] / total_prs * 100) if total_prs > 0 else 0, 1),
            'merged_prs': metrics['merged_prs'],
            'merged_prs_percentage': round((metrics['merged_prs'] / total_prs * 100) if total_prs > 0 else 0, 1),
            'closed_prs': metrics['closed_prs'],
            'prs_without_review': prs_without_review,
            'prs_without_review_rate': round((prs_without_review / total_prs * 100) if total_prs > 0 else 0, 1),
            'self_merged_prs': self_merged_prs,
            'self_merged_rate': round((self_merged_prs / total_prs * 100) if total_prs > 0 else 0, 1),
            'old_open_prs': metrics['old_open_prs'],
            'old_open_prs_rate': round((metrics['old_open_prs'] / total_prs * 100) if total_prs > 0 else 0, 1),
            'avg_merge_time_hours': round(avg_merge_time_hours, 1),
            'median_merge_time_hours': round(median_merge_time, 1)
        }
        
        # Cache the results
        AnalyticsCacheService.set_pr_health_metrics(application.id, result_metrics)
        
        return result_metrics
        
    except Exception as e:
        print(f"Error generating PR health metrics: {e}")
        return {
            'total_prs': 0,
            'open_prs': 0,
            'merged_prs': 0,
            'closed_prs': 0,
            'prs_without_review': 0,
            'prs_without_review_rate': 0,
            'self_merged_prs': 0,
            'self_merged_rate': 0,
            'old_open_prs': 0,
            'old_open_prs_rate': 0,
            'avg_merge_time_hours': 0,
            'median_merge_time_hours': 0
        }


@login_required
@require_http_methods(["GET"])
def api_pr_health_metrics(request, pk):
    """API endpoint to get PR health metrics asynchronously"""
    try:
        application = get_object_or_404(Application, pk=pk)
        
        # Check if user has access to this application
        if application.owner != request.user:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Generate or get from cache
        metrics = _generate_pr_health_metrics(application)
        
        return JsonResponse({
            'success': True,
            'metrics': metrics,
            'cached': AnalyticsCacheService.get_pr_health_metrics(application.id) is not None
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
