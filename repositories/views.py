import os
print(f"[DEBUG] {os.path.abspath(__file__)} loaded (views.py)")
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import Repository
from analytics.github_token_service import GitHubTokenService
from analytics.unified_metrics_service import UnifiedMetricsService


@login_required
def repository_list(request):
    """List all indexed repositories"""
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Filter repositories
    repositories = Repository.objects.filter(owner=request.user)
    
    if search_query:
        repositories = repositories.filter(
            Q(name__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(repositories, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Stats
    total_repos = repositories.count()
    indexed_repos = repositories.filter(is_indexed=True).count()
    total_commits = repositories.aggregate(total=Sum('commit_count'))['total'] or 0
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'total_repos': total_repos,
        'indexed_repos': indexed_repos,
        'total_commits': total_commits,
    }
    
    return render(request, 'repositories/list.html', context)


@login_required
def repository_detail(request, repo_id):
    """Display repository details and analytics dashboard"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        messages.error(request, "Repository not found.")
        return redirect('repositories:list')

    # Récupère la plage de dates depuis les paramètres GET
    from datetime import datetime, timedelta
    from django.utils import timezone
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    if start_str and end_str:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d")
        except Exception:
            start_date = timezone.now() - timedelta(days=29)
            end_date = timezone.now()
    else:
        end_date = timezone.now()
        start_date = end_date - timedelta(days=29)
    print(f"[DEBUG] repository_detail: start_date={start_date}, end_date={end_date}")
    # Utilise la plage pour filtrer les stats
    try:
        metrics_service = UnifiedMetricsService('repository', repo_id, start_date=start_date, end_date=end_date)
        
        # Get all metrics using the unified service
        all_metrics = metrics_service.get_all_metrics()
        
        # Debug logging removed for now
        
        # Extract specific metrics for template
        overall_stats = {
            'total_commits': all_metrics['total_commits'],
            'total_authors': all_metrics['total_developers'],
            'total_additions': all_metrics['lines_added'],
            'total_deletions': all_metrics['lines_deleted'],
            'net_lines': all_metrics['net_lines']
        }
        
        developer_activity = all_metrics['developer_activity_30d']
        commit_frequency = all_metrics['commit_frequency']
        release_frequency = all_metrics['release_frequency']
        total_releases = all_metrics['total_releases']
        pr_cycle_time = all_metrics['pr_cycle_time']
        commit_quality = all_metrics['commit_quality']
        commit_types = all_metrics['commit_type_distribution']
        pr_health_metrics = all_metrics['pr_health_metrics']
        top_contributors = all_metrics['top_contributors']
        activity_heatmap = all_metrics['commit_activity_by_hour']
        
        # Calculate PR cycle time statistics for template
        pr_cycle_time_median = pr_cycle_time.get('median_cycle_time_hours', 0)
        pr_cycle_time_avg = pr_cycle_time.get('avg_cycle_time_hours', 0)
        pr_cycle_time_count = pr_cycle_time.get('total_prs', 0)
        
        # Prepare chart data for doughnut chart (like applications)
        commit_types_counts = commit_types.get('counts', {}) if isinstance(commit_types, dict) else {}
        commit_type_labels = json.dumps(list(commit_types_counts.keys()))
        commit_type_values = json.dumps(list(commit_types_counts.values()))
        
        # Doughnut colors for commit types
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
        
        # Legend data for commit types
        legend_data = []
        for label, count in commit_types_counts.items():
            color = doughnut_colors.get(label, '#bdbdbd')
            legend_data.append({'label': label, 'count': count, 'color': color})
        
        # Hourly activity data
        hourly_data = activity_heatmap.get('hourly_data', {})
        activity_heatmap_data = json.dumps([int(hourly_data.get(str(hour), 0)) for hour in range(24)])
        
        context = {
            'repository': repository,
            'overall_stats': overall_stats,
            'developer_activity': developer_activity,
            'commit_frequency': commit_frequency,
            'release_frequency': release_frequency,
            'total_releases': total_releases,
            'pr_cycle_time_median': pr_cycle_time_median,
            'pr_cycle_time_avg': pr_cycle_time_avg,
            'pr_cycle_time_count': pr_cycle_time_count,
            'commit_quality': commit_quality,
            'commit_types': commit_types,
            'pr_health_metrics': pr_health_metrics,
            'top_contributors': top_contributors,
            'activity_heatmap': activity_heatmap,
            
            # Chart data
            'commit_type_labels': commit_type_labels,
            'commit_type_values': commit_type_values,
            'commit_type_legend': legend_data,
            'doughnut_colors': doughnut_colors,
            'activity_heatmap_data': activity_heatmap_data,
        }
        
    except Exception as e:
        # If metrics calculation fails, provide empty data and log the error
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting metrics for repository {repo_id}: {e}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        context = {
            'repository': repository,
            'overall_stats': {'total_commits': 0, 'total_authors': 0, 'total_additions': 0, 'total_deletions': 0, 'net_lines': 0},
            'developer_activity': {'developers': []},
            'commit_frequency': {'avg_commits_per_day': 0, 'recent_activity_score': 0, 'consistency_score': 0, 'overall_frequency_score': 0, 'commits_last_30_days': 0, 'commits_last_90_days': 0, 'days_since_last_commit': None, 'active_days': 0, 'total_days': 0},
            'release_frequency': {'releases_per_month': 0, 'releases_per_week': 0, 'total_releases': 0, 'period_days': 90},
            'total_releases': 0,
            'pr_cycle_time_median': 0,
            'pr_cycle_time_avg': 0,
            'pr_cycle_time_count': 0,
            'commit_quality': {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0},
            'commit_types': {'counts': {}},
            'pr_health_metrics': {'total_prs': 0, 'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0, 'prs_without_review': 0, 'prs_without_review_rate': 0, 'self_merged_prs': 0, 'self_merged_rate': 0, 'old_open_prs': 0, 'old_open_prs_rate': 0, 'avg_merge_time_hours': 0, 'median_merge_time_hours': 0},
            'top_contributors': [],
            'activity_heatmap': {'hourly_data': {}, 'total_commits': 0, 'period_days': 30},
            'commit_type_labels': json.dumps([]),
            'commit_type_values': json.dumps([]),
            'commit_type_legend': [],
            'doughnut_colors': {},
            'activity_heatmap_data': json.dumps([0] * 24),
            'error': str(e),
            'debug_error': True
        }
    
    # Removed debug code for now
    
    return render(request, 'repositories/detail.html', context)


@login_required
def search_repositories(request):
    """Search repositories on GitHub"""
    query = request.GET.get('q', '').lower()
    
    try:
        # Get user's GitHub token for repository access
        github_token = GitHubTokenService.get_token_for_operation('private_repos', request.user.id)
        if not github_token:
            return JsonResponse({'error': 'GitHub token not found'}, status=401)
        
        from analytics.github_service import GitHubService
        github_service = GitHubService(github_token)
        
        # Get user's repositories (like in applications app)
        all_repos = []
        page = 1
        while True:
            url = 'https://api.github.com/user/repos'
            params = {
                'sort': 'updated',
                'per_page': 100,
                'type': 'all',  # Include private repos
                'page': page
            }
            
            repos_data, _ = github_service._make_request(url, params)
            
            if repos_data is not None:
                if not repos_data:
                    break
                all_repos.extend(repos_data)
                page += 1
                if page > 10:  # Limit to 1000 repos max
                    break
            else:
                return JsonResponse({'error': 'GitHub API error'}, status=500)
        
        # Récupère les github_id déjà indexés pour cet utilisateur
        from .models import Repository
        existing_github_ids = set(Repository.objects.filter(owner=request.user).values_list('github_id', flat=True))
        # Filter repositories based on query and exclude already indexed
        filtered_repos = []
        for repo in all_repos:
            # Check if repo name or description contains the query
            repo_name = repo['name'].lower()
            repo_full_name = repo['full_name'].lower()
            repo_description = (repo.get('description', '') or '').lower()
            
            if (query in repo_name or 
                query in repo_full_name or 
                query in repo_description):
                if repo['id'] not in existing_github_ids:
                    filtered_repos.append({
                        'id': repo['id'],
                        'name': repo['name'],
                        'full_name': repo['full_name'],
                        'description': repo.get('description', ''),
                        'private': repo['private'],
                        'fork': repo['fork'],
                        'language': repo.get('language'),
                        'stargazers_count': repo['stargazers_count'],
                        'forks_count': repo['forks_count'],
                        'size': repo['size'],
                        'default_branch': repo['default_branch'],
                        'html_url': repo['html_url'],
                        'clone_url': repo['clone_url'],
                        'ssh_url': repo['ssh_url']
                    })
        
        # Sort by stars (descending) and limit to 10 results
        filtered_repos.sort(key=lambda x: x['stargazers_count'], reverse=True)
        filtered_repos = filtered_repos[:10]
        
        return JsonResponse({'repositories': filtered_repos})
        
    except Exception as e:
        return JsonResponse({'error': f'Error searching repositories: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def index_repository(request):
    """Index a repository"""
    try:
        repository_data = json.loads(request.POST.get('repository_data', '{}'))
        
        if not repository_data:
            return JsonResponse({'success': False, 'error': 'No repository data provided'})
        
        # Check if repository already exists
        existing_repo = Repository.objects.filter(
            github_id=repository_data['id'],
            owner=request.user
        ).first()
        
        if existing_repo:
            return JsonResponse({'success': False, 'error': 'Repository already indexed'})
        
        # Create repository record
        repository = Repository.objects.create(
            name=repository_data['name'],
            full_name=repository_data['full_name'],
            description=repository_data.get('description', ''),
            private=repository_data['private'],
            fork=repository_data['fork'],
            language=repository_data.get('language'),
            stars=repository_data['stargazers_count'],
            forks=repository_data['forks_count'],
            size=repository_data['size'],
            default_branch=repository_data['default_branch'],
            github_id=repository_data['id'],
            html_url=repository_data['html_url'],
            clone_url=repository_data['clone_url'],
            ssh_url=repository_data['ssh_url'],
            owner=request.user
        )
        
        # Just add to database, don't start indexing yet
        repository.is_indexed = False
        repository.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Repository {repository.full_name} added successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid repository data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error indexing repository: {str(e)}'})


@login_required
def repository_detail(request, repo_id):
    """Show repository details"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        messages.error(request, 'Repository not found.')
        return redirect('repositories:list')
    
    context = {
        'repository': repository,
    }
    
    return render(request, 'repositories/detail.html', context)


@login_required
@require_http_methods(["POST"])
def start_indexing(request, repo_id):
    """Start indexing for a specific repository"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'})
    
    try:
        from analytics.tasks import background_indexing_task
        from django_q.tasks import async_task
        
        # Schedule background indexing task
        task_id = async_task(
            'analytics.tasks.background_indexing_task',
            repository.id,
            request.user.id,
            group=f'indexing_{repository.id}',
            timeout=3600  # 1 hour timeout
        )
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': f'Indexing started for repository {repository.full_name}'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error starting indexing: {str(e)}'})


@login_required
@require_http_methods(["POST"])
def delete_repository(request, repo_id):
    """Delete a repository and all its associated data"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'})
    
    try:
        from analytics.models import Commit, PullRequest, Release, Deployment, RepositoryStats, SyncLog
        
        # Delete all associated data from MongoDB
        deleted_counts = {
            'commits': 0,
            'pull_requests': 0,
            'releases': 0,
            'deployments': 0,
            'repository_stats': 0,
            'sync_logs': 0
        }
        
        # Delete commits
        commits = Commit.objects(repository_full_name=repository.full_name)
        deleted_counts['commits'] = commits.count()
        commits.delete()
        
        # Delete pull requests
        pull_requests = PullRequest.objects(repository_full_name=repository.full_name)
        deleted_counts['pull_requests'] = pull_requests.count()
        pull_requests.delete()
        
        # Delete releases
        releases = Release.objects(repository_full_name=repository.full_name)
        deleted_counts['releases'] = releases.count()
        releases.delete()
        
        # Delete deployments
        deployments = Deployment.objects(repository_full_name=repository.full_name)
        deleted_counts['deployments'] = deployments.count()
        deployments.delete()
        
        # Delete repository stats
        repo_stats = RepositoryStats.objects(repository_full_name=repository.full_name)
        deleted_counts['repository_stats'] = repo_stats.count()
        repo_stats.delete()
        
        # Delete sync logs
        sync_logs = SyncLog.objects(repository_full_name=repository.full_name)
        deleted_counts['sync_logs'] = sync_logs.count()
        sync_logs.delete()
        
        # Delete the repository from Django DB
        repository.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Repository {repository.full_name} deleted successfully',
            'deleted_counts': deleted_counts
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error deleting repository: {str(e)}'})


@login_required
@require_http_methods(["GET"])
def api_repository_pr_health_metrics(request, repo_id):
    """API endpoint to get PR health metrics for a repository asynchronously"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
        
        # Use unified metrics service
        metrics_service = UnifiedMetricsService('repository', repo_id)
        metrics = metrics_service.get_pr_health_metrics()
        
        return JsonResponse({
            'success': True,
            'metrics': metrics
        })
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_repository_developer_activity(request, repo_id):
    """API endpoint for repository developer activity data"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
        
        # Get period from query params
        days = int(request.GET.get('days', 30))
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_developer_activity(days=days)
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_repository_commit_quality(request, repo_id):
    """API endpoint for repository commit quality metrics"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_commit_quality()
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_repository_commit_types(request, repo_id):
    """API endpoint for repository commit type distribution"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_commit_type_distribution()
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def index_repositories(request):
    """Batch add repositories"""
    try:
        repositories_data = json.loads(request.POST.get('repositories_data', '[]'))
        if not repositories_data:
            return JsonResponse({'success': False, 'error': 'No repositories data provided'})
        added = 0
        skipped = 0
        for repository_data in repositories_data:
            if Repository.objects.filter(github_id=repository_data['id'], owner=request.user).exists():
                skipped += 1
                continue
            Repository.objects.create(
                name=repository_data['name'],
                full_name=repository_data['full_name'],
                description=repository_data.get('description', ''),
                private=repository_data['private'],
                fork=repository_data['fork'],
                language=repository_data.get('language'),
                stars=repository_data['stargazers_count'],
                forks=repository_data['forks_count'],
                size=repository_data['size'],
                default_branch=repository_data['default_branch'],
                github_id=repository_data['id'],
                html_url=repository_data['html_url'],
                clone_url=repository_data['clone_url'],
                ssh_url=repository_data['ssh_url'],
                owner=request.user,
                is_indexed=False,
                is_indexing=False
            )
            added += 1
        return JsonResponse({'success': True, 'added': added, 'skipped': skipped})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error adding repositories: {str(e)}'})
