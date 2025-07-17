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

from .models import Application, ApplicationRepository
from .forms import ApplicationForm, RepositorySelectionForm
from github.models import GitHubToken


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
    if not request.user.is_superuser:
        return redirect('applications:list')
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
    application = get_object_or_404(Application, pk=pk)
    repositories = application.repositories.all()
    
    # Get analytics data
    try:
        from analytics.analytics_service import AnalyticsService
        analytics = AnalyticsService(pk)
        
        # Get commit frequency with error handling
        try:
            commit_frequency = analytics.get_application_commit_frequency()
        except Exception as e:
            print(f"Error getting commit frequency: {e}")
            commit_frequency = {
                'avg_commits_per_day': 0,
                'recent_activity_score': 0,
                'consistency_score': 0,
                'overall_frequency_score': 0,
                'commits_last_30_days': 0,
                'commits_last_90_days': 0,
                'days_since_last_commit': None,
                'active_days': 0,
                'total_days': 0
            }
        
        # Get application quality metrics
        application_quality_metrics = _generate_application_quality_metrics(application)
        
        # Get analytics data
        overall_stats = analytics.get_overall_stats()
        developer_activity = analytics.get_developer_activity(days=30)
        # Ajout pour active developers sur 120 jours
        developer_activity_120d = analytics.get_developer_activity(days=120)
        active_developers_count_120d = len(developer_activity_120d.get('developers', []))
        # Suppression des variables de debug liées aux PRs
        
        # Ajout : fréquence de release (30 jours)
        try:
            release_frequency = analytics.get_release_frequency(period_days=30)
        except Exception as e:
            print(f"Error getting release frequency: {e}")
            release_frequency = {
                'releases_per_month': 0,
                'releases_per_week': 0,
                'total_releases': 0,
                'period_days': 30,
            }

        # Ajout : total releases toutes périodes
        try:
            total_releases = analytics.get_total_releases()
        except Exception as e:
            print(f"Error getting total releases: {e}")
            total_releases = 0
        
        # Calcul PR Cycle Time (médiane, min, max, count)
        pr_cycle_times = analytics.get_pr_cycle_times()
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
    """Edit an existing application"""
    if not (request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied
    application = get_object_or_404(Application, pk=pk)
    
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
    if not (request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied
    application = get_object_or_404(Application, pk=pk)
    
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
@require_http_methods(["GET"])
def api_get_repositories(request, pk):
    """API endpoint to get GitHub repositories with caching and real-time search"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    
    # Get user's GitHub token
    try:
        github_token = GitHubToken.objects.get(user=request.user)
    except GitHubToken.DoesNotExist:
        return JsonResponse({'error': 'GitHub token not found'}, status=401)
    
    # Get search query
    search_query = request.GET.get('search', '').lower()
    
    # Get existing repos for this application
    existing_repos = list(application.repositories.values_list('github_repo_name', flat=True))
    
    try:
        headers = {
            'Authorization': f'token {github_token.access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get user's repositories
        all_repos = []
        page = 1
        while True:
            response = requests.get('https://api.github.com/user/repos', headers=headers, params={
                'sort': 'updated',
                'per_page': 100,
                'type': 'all',
                'page': page
            })
            
            if response.status_code == 200:
                repos_page = response.json()
                if not repos_page:
                    break
                all_repos.extend(repos_page)
                page += 1
                if page > 10:
                    break
            else:
                return JsonResponse({'error': f'GitHub API error: {response.status_code}'}, status=500)
        
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
def remove_repository(request, pk, repo_id):
    """Remove a repository from an application"""
    application = get_object_or_404(Application, pk=pk, owner=request.user)
    repository = get_object_or_404(ApplicationRepository, pk=repo_id, application=application)
    
    if request.method == 'POST':
        repo_name = repository.github_repo_name
        
        # Clean up MongoDB data before deleting the repository
        try:
            from analytics.services import cleanup_repository_data
            cleanup_results = cleanup_repository_data(repo_name)
            
            if 'error' in cleanup_results:
                messages.warning(request, f'Repository removed but some data cleanup failed: {cleanup_results["error"]}')
            else:
                if cleanup_results['total_deleted'] > 0:
                    messages.info(request, f'Cleaned up {cleanup_results["total_deleted"]} MongoDB records.')
        except ImportError:
            # If analytics app is not available, just delete the repository
            pass
        except Exception as e:
            # If cleanup fails, still delete the repository but warn the user
            messages.warning(request, f'Repository removed but data cleanup failed: {str(e)}')
        
        # Delete the repository
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


def _generate_application_quality_metrics(application):
    """Generate quality metrics data for an application from MongoDB collection"""
    from pymongo import MongoClient
    from datetime import datetime, timedelta, timezone
    
    try:
        # Connect to MongoDB
        client = MongoClient('localhost', 27017)
        db = client['gitpulse']
        quality_collection = db['developer_quality_metrics']
        
        # Get all repository names for this application
        repository_names = list(application.repositories.values_list('github_repo_name', flat=True))
        
        if not repository_names:
            return {
                'total_commits': 0,
                'avg_code_quality': 0,
                'avg_impact': 0,
                'avg_complexity': 0,
                'suspicious_commits': 0,
                'suspicious_ratio': 0,
                'real_code_commits': 0,
                'real_code_ratio': 0,
                'doc_only_commits': 0,
                'config_only_commits': 0,
                'micro_commits': 0,
                'no_ticket_commits': 0
            }
        
        # Query MongoDB for quality metrics for this application
        # Since we don't have application_id in MongoDB, we'll filter by repository names
        pipeline = [
            {
                '$match': {
                    'repository': {'$in': repository_names}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total_commits': {'$sum': 1},
                    'avg_code_quality': {'$avg': '$code_quality_score'},
                    'avg_impact': {'$avg': '$impact_score'},
                    'avg_complexity': {'$avg': '$complexity_score'},
                    'suspicious_commits': {
                        '$sum': {
                            '$cond': [
                                {
                                    '$gt': [
                                        {
                                            '$size': {
                                                '$filter': {
                                                    'input': '$suspicious_patterns',
                                                    'cond': {'$ne': ['$$this', 'no_ticket_reference']}
                                                }
                                            }
                                        },
                                        0
                                    ]
                                },
                                1,
                                0
                            ]
                        }
                    },
                    'real_code_commits': {
                        '$sum': {'$cond': ['$is_real_code', 1, 0]}
                    },
                    'doc_only_commits': {
                        '$sum': {'$cond': ['$is_documentation_only', 1, 0]}
                    },
                    'config_only_commits': {
                        '$sum': {'$cond': ['$is_config_only', 1, 0]}
                    },
                    'micro_commits': {
                        '$sum': {'$cond': [{'$in': ['micro_commit', '$suspicious_patterns']}, 1, 0]}
                    },
                    'no_ticket_commits': {
                        '$sum': {'$cond': [{'$in': ['no_ticket_reference', '$suspicious_patterns']}, 1, 0]}
                    }
                }
            }
        ]
        
        result = list(quality_collection.aggregate(pipeline))
        
        if not result:
            return {
                'total_commits': 0,
                'avg_code_quality': 0,
                'avg_impact': 0,
                'avg_complexity': 0,
                'suspicious_commits': 0,
                'suspicious_ratio': 0,
                'real_code_commits': 0,
                'real_code_ratio': 0,
                'doc_only_commits': 0,
                'config_only_commits': 0,
                'micro_commits': 0,
                'no_ticket_commits': 0
            }
        
        data = result[0]
        total_commits = data.get('total_commits', 0)
        
        return {
            'total_commits': total_commits,
            'avg_code_quality': round(data.get('avg_code_quality', 0), 1),
            'avg_impact': round(data.get('avg_impact', 0), 1),
            'avg_complexity': round(data.get('avg_complexity', 0), 1),
            'suspicious_commits': data.get('suspicious_commits', 0),
            'suspicious_ratio': round((data.get('suspicious_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1),
            'real_code_commits': data.get('real_code_commits', 0),
            'real_code_ratio': round((data.get('real_code_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1),
            'doc_only_commits': data.get('doc_only_commits', 0),
            'doc_only_ratio': round((data.get('doc_only_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1),
            'config_only_commits': data.get('config_only_commits', 0),
            'config_only_ratio': round((data.get('config_only_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1),
            'micro_commits': data.get('micro_commits', 0),
            'micro_commits_ratio': round((data.get('micro_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1),
            'no_ticket_commits': data.get('no_ticket_commits', 0),
            'no_ticket_ratio': round((data.get('no_ticket_commits', 0) / total_commits * 100) if total_commits > 0 else 0, 1)
        }
        
    except Exception as e:
        print(f"Error generating application quality metrics: {e}")
        return {
            'total_commits': 0,
            'avg_code_quality': 0,
            'avg_impact': 0,
            'avg_complexity': 0,
            'suspicious_commits': 0,
            'suspicious_ratio': 0,
            'real_code_commits': 0,
            'real_code_ratio': 0,
            'doc_only_commits': 0,
            'config_only_commits': 0,
            'micro_commits': 0,
            'no_ticket_commits': 0
        }
