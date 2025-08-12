import json
from datetime import datetime, timedelta
import logging
import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from analytics.codeql_indexing_service import get_codeql_indexing_service_for_user
from analytics.codeql_service import get_codeql_service_for_user
from analytics.github_token_service import GitHubTokenService
from analytics.license_analysis_service import LicenseAnalysisService
from analytics.llm_service import LLMService
from analytics.sanitization import assert_safe_repository_full_name
from analytics.sonarcloud_service import SonarCloudService
from analytics.unified_metrics_service import UnifiedMetricsService
from .models import Repository
logger = logging.getLogger(__name__)

def staff_required(view_func):
    """Decorator to require SuperUser or Staff permissions"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have permission to perform this action.")
            return redirect('repositories:list')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def _error_response(user_message: str, exc: Exception = None, status: int = 500):
    error_id = str(uuid.uuid4())
    if exc is not None:
        logger.exception("%s [error_id=%s]", user_message, error_id)
    else:
        logger.error("%s [error_id=%s]", user_message, error_id)
    return JsonResponse({'success': False, 'message': user_message, 'error_id': error_id}, status=status)

def _get_sonarcloud_metrics(repository_id: int):
    """Get latest SonarCloud metrics for a repository"""
    try:
        sonar_service = SonarCloudService()
        return sonar_service.get_latest_metrics(repository_id)
    except Exception:
        logger.exception("Error getting SonarCloud metrics for repository %s", repository_id)
        return None


def _is_sonarcloud_configured():
    """Check if SonarCloud is configured (token exists)"""
    try:
        from sonarcloud.models import SonarCloudConfig
        config = SonarCloudConfig.get_config()
        return bool(config.access_token)
    except Exception:
        logger.exception("Error checking SonarCloud configuration")
        return False


def _get_codeql_metrics(repository, user_id: int):
    """Get latest CodeQL metrics for a repository"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get CodeQL indexing service
        indexing_service = get_codeql_indexing_service_for_user(user_id)
        
        # Get repository security metrics with SHS
        metrics = indexing_service.get_repository_security_metrics(repository.full_name, repository.id)
        
        # Add status information
        if metrics['total_vulnerabilities'] == 0 and metrics.get('latest_analysis') is None:
            # No data at all - likely CodeQL not available
            metrics['status'] = 'not_available'
        else:
            metrics['status'] = 'available'
        
        logger.info("Retrieved CodeQL metrics for %s: %s vulnerabilities, SHS: %s", repository.full_name, metrics['total_vulnerabilities'], metrics.get('shs_display', 'N/A'))
        return metrics
        
    except Exception:
        error_id = str(uuid.uuid4())
        logger.exception("Error getting CodeQL metrics for repository %s [error_id=%s]", repository.full_name, error_id)
        return {
            'status': 'not_available',
            'shs_score': None,
            'shs_display': 'Error',
            'shs_message': 'CodeQL metrics unavailable',
            'error_id': error_id,
            'delta_shs': 0.0,
            'total_vulnerabilities': 0,
            'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
            'latest_analysis': None
        }


@login_required
def repository_list(request):
    """List all indexed repositories"""
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Get sort parameters
    sort_by = request.GET.get('sort', 'full_name')
    order = request.GET.get('order', 'asc')
    
    # Validate sort fields
    allowed_sort_fields = ['name', 'full_name', 'language', 'kloc', 'is_indexed', 'created_at']
    if sort_by not in allowed_sort_fields:
        sort_by = 'full_name'
    
    # Build order_by
    if order == 'desc':
        sort_by = f'-{sort_by}'
    
    # Filter repositories and sort (all repositories visible to all users)
    repositories = Repository.objects.all().order_by(sort_by)
    
    if search_query:
        repositories = repositories.filter(
            Q(name__icontains=search_query) |
            Q(full_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(repositories, 50)  # Increased page size for better UX
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Stats
    total_repos = repositories.count()
    indexed_repos = repositories.filter(is_indexed=True).count()
    total_commits = repositories.aggregate(total=Sum('commit_count'))['total'] or 0
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        repos_data = []
        for repo in page_obj:
            repos_data.append({
                'id': repo.id,
                'name': repo.name,
                'full_name': repo.full_name,
                'description': repo.description or '',
                'language': repo.language or '',
                'kloc': repo.kloc,
                'is_indexed': repo.is_indexed,
                'private': repo.private,
                'fork': repo.fork,
                'html_url': repo.html_url,
                'commit_count': repo.commit_count,
            })
        
        return JsonResponse({
            'repositories': repos_data,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'total_count': total_repos,
        })
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'sort_by': sort_by.replace('-', '') if sort_by.startswith('-') else sort_by,
        'order': order,
        'total_repos': total_repos,
        'indexed_repos': indexed_repos,
        'total_commits': total_commits,
    }
    
    return render(request, 'repositories/list.html', context)


@login_required
def repository_detail(request, repo_id):
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
    # Passe la plage à UnifiedMetricsService
    metrics_service = UnifiedMetricsService('repository', repo_id, start_date=start_date, end_date=end_date)
    all_metrics = metrics_service.get_all_metrics()
    
    """Working repository detail view with proper charts"""
    try:
        repository = Repository.objects.get(id=repo_id)
        # Validate before using repository.full_name in Mongo queries
        assert_safe_repository_full_name(repository.full_name)
    except Repository.DoesNotExist:
        messages.error(request, "Repository not found.")
        return redirect('repositories:list')
    
    if not repository.is_indexed:
        context = {
            'repository': repository,
            'error_message': 'Repository is not indexed yet'
        }
        return render(request, 'repositories/detail.html', context)
    
    try:
        # Get metrics using unified service
        # metrics_service = UnifiedMetricsService('repository', repo_id)
        # all_metrics = metrics_service.get_all_metrics()
        
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
        deployment_frequency = all_metrics['deployment_frequency']
        total_deployments = all_metrics['total_deployments']
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
        
        # Bubble chart data
        bubble_chart = metrics_service.get_bubble_chart_data(days=30)
        bubble_chart_data = json.dumps(bubble_chart.get('datasets', []))
        
        # Ajout stats changements commit (calcul et conversion explicite)
        commit_change_stats = all_metrics['commit_change_stats']
        avg_total_changes = round(float(commit_change_stats.get('avg_total_changes', 0)), 2)
        avg_files_changed = round(float(commit_change_stats.get('avg_files_changed', 0)), 2)
        nb_commits = int(commit_change_stats.get('nb_commits', 0))
        
        # Get SBOM data (no longer using SBOMVulnerability; vulnerabilities come from CodeQL)
        from analytics.models import SBOM
        # Get all SBOMs for this repository (full_name already validated above)
        assert_safe_repository_full_name(repository.full_name)
        all_sboms = SBOM.objects(repository_full_name=repository.full_name).order_by('-generated_at')
        
        # Choose the most recent SBOM if available
        sbom = all_sboms[0] if all_sboms else None
        vulnerability_stats = {
            'total_vulnerabilities': 0,
            'severity_counts': {},
            'has_sbom': False
        }
        
        if sbom:
            # Apply date filtering to SBOM generation date
            sbom_in_range = True
            if start_date and end_date:
                try:
                    # Convert date objects to timezone-aware datetime
                    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
                    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.min.time()))
                    # Add one day to end_date to include the full day
                    end_dt = end_dt + timedelta(days=1)
                    
                    # Check if SBOM was generated within the date range
                    if sbom.generated_at:
                        sbom_date = sbom.generated_at
                        # Ensure SBOM date is timezone-aware
                        if sbom_date.tzinfo is None:
                            sbom_date = timezone.make_aware(sbom_date)
                        if sbom_date < start_dt or sbom_date >= end_dt:
                            sbom_in_range = False
                except ValueError:
                    # Invalid date format, continue without filtering
                    pass
            
            if sbom_in_range:
                # We only expose CodeQL vulnerabilities now; keep SBOM presence as a flag
                vulnerability_stats['has_sbom'] = True
        
        # Get SonarCloud metrics
        from repositories.views import _get_sonarcloud_metrics
        sonarcloud_metrics = _get_sonarcloud_metrics(repository.id)
        print(f"DEBUG: sonarcloud_metrics = {sonarcloud_metrics}")
        print(f"DEBUG: sonarcloud_metrics type = {type(sonarcloud_metrics)}")
        if sonarcloud_metrics:
            print(f"DEBUG: sonarcloud_metrics.quality_gate = {sonarcloud_metrics.quality_gate}")
        
        # Get CodeQL metrics
        codeql_metrics = _get_codeql_metrics(repository, request.user.id)
        
        # Build context
        context = {
            'repository': repository,
            'start_date': start_date.strftime("%Y-%m-%d"),
            'end_date': end_date.strftime("%Y-%m-%d"),
            'overall_stats': overall_stats,
            'developer_activity': developer_activity,
            'commit_frequency': commit_frequency,
            'release_frequency': release_frequency,
            'total_releases': total_releases,
            'deployment_frequency': deployment_frequency,
            'total_deployments': total_deployments,
            'pr_cycle_time_median': pr_cycle_time_median,
            'pr_cycle_time_avg': pr_cycle_time_avg,
            'pr_cycle_time_count': pr_cycle_time_count,
            'commit_quality': commit_quality,
            'commit_types': commit_types,
            'pr_health_metrics': pr_health_metrics,
            'top_contributors': top_contributors,
            'activity_heatmap': activity_heatmap,
            'commit_type_labels': commit_type_labels,
            'commit_type_values': commit_type_values,
            'commit_type_legend': legend_data,
            'doughnut_colors': doughnut_colors,
            'activity_heatmap_data': activity_heatmap_data,
            'bubble_chart_data': bubble_chart_data,
            'commit_change_stats': {
                'avg_total_changes': avg_total_changes,
                'avg_files_changed': avg_files_changed,
                'nb_commits': nb_commits,
            },
            'vulnerability_stats': vulnerability_stats,
            'sonarcloud_metrics': sonarcloud_metrics,
            'codeql_metrics': codeql_metrics,
        }
        
    except Exception as e:
        # If metrics calculation fails, provide empty data
        context = {
            'repository': repository,
            'start_date': start_date.strftime("%Y-%m-%d"),
            'end_date': end_date.strftime("%Y-%m-%d"),
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
            'sonarcloud_metrics': None,
            'error_message': 'Failed to compute repository metrics',
            'error_id': str(uuid.uuid4())
        }
    
    return render(request, 'repositories/detail.html', context)


@login_required
@require_http_methods(["GET"])
def repository_sonarcloud_temporal(request, repo_id):
    """Get temporal analysis of SonarCloud metrics for a repository"""
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get date range from query parameters
        from_date_str = request.GET.get('from')
        to_date_str = request.GET.get('to')
        
        from_date = None
        to_date = None
        
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
            except ValueError:
                pass
        
        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
            except ValueError:
                pass
        
        # Get temporal analysis from SonarCloud service
        sonar_service = SonarCloudService()
        
        temporal_data = sonar_service.get_temporal_analysis(
            repository_id=repo_id,
            repository_full_name=repository.full_name,
            from_date=from_date,
            to_date=to_date
        )
        
        return JsonResponse({
            'success': True,
            'repository_id': repo_id,
            'repository_name': repository.full_name,
            'data': temporal_data
        })
        
    except Exception as e:
        logger.exception("Error getting SonarCloud temporal analysis for repository %s", repo_id)
        return _error_response('Error retrieving SonarCloud temporal analysis', exc=e)


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
        existing_github_ids = set(Repository.objects.all().values_list('github_id', flat=True))
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
        return _error_response('Error searching repositories', exc=e)


@login_required
@staff_required
@require_http_methods(["POST"])
def index_repository(request):
    """Index a repository"""
    try:
        repository_data = json.loads(request.POST.get('repository_data', '{}'))
        
        if not repository_data:
            return JsonResponse({'success': False, 'error': 'No repository data provided'})
        
        # Check if repository already exists
        existing_repo = Repository.objects.filter(
            github_id=repository_data['id']
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
            owner=request.user  # Keep owner for tracking who added it
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
        return _error_response('Error indexing repository', exc=e)


@login_required
@staff_required
@require_http_methods(["POST"])
def start_indexing(request, repo_id):
    """Start indexing for a specific repository"""
    try:
        repository = Repository.objects.get(id=repo_id)
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
        return _error_response('Error starting indexing', exc=e)


@login_required
@staff_required
@require_http_methods(["POST"])
def delete_repository(request, repo_id):
    """Delete a repository and all its associated data"""
    try:
        repository = Repository.objects.get(id=repo_id)
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
        assert_safe_repository_full_name(repository.full_name)
        commits = Commit.objects(repository_full_name=repository.full_name)
        deleted_counts['commits'] = commits.count()
        commits.delete()
        
        # Delete pull requests
        assert_safe_repository_full_name(repository.full_name)
        pull_requests = PullRequest.objects(repository_full_name=repository.full_name)
        deleted_counts['pull_requests'] = pull_requests.count()
        pull_requests.delete()
        
        # Delete releases
        assert_safe_repository_full_name(repository.full_name)
        releases = Release.objects(repository_full_name=repository.full_name)
        deleted_counts['releases'] = releases.count()
        releases.delete()
        
        # Delete deployments
        assert_safe_repository_full_name(repository.full_name)
        deployments = Deployment.objects(repository_full_name=repository.full_name)
        deleted_counts['deployments'] = deployments.count()
        deployments.delete()
        
        # Delete repository stats
        assert_safe_repository_full_name(repository.full_name)
        repo_stats = RepositoryStats.objects(repository_full_name=repository.full_name)
        deleted_counts['repository_stats'] = repo_stats.count()
        repo_stats.delete()
        
        # Delete sync logs
        assert_safe_repository_full_name(repository.full_name)
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
        return _error_response('Error deleting repository', exc=e)


@login_required
@require_http_methods(["GET"])
def api_repository_pr_health_metrics(request, repo_id):
    """API endpoint to get PR health metrics for a repository asynchronously"""
    try:
        repository = Repository.objects.get(id=repo_id)
        
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
        return _error_response('Error retrieving PR health metrics', exc=e)


@login_required
@require_http_methods(["GET"])
def api_repository_developer_activity(request, repo_id):
    """API endpoint for repository developer activity data"""
    try:
        repository = Repository.objects.get(id=repo_id)
        
        # Get period from query params
        days = int(request.GET.get('days', 30))
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_developer_activity(days=days)
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return _error_response('Error retrieving developer activity', exc=e)


@login_required
@require_http_methods(["GET"])
def api_repository_commit_quality(request, repo_id):
    """API endpoint for repository commit quality metrics"""
    try:
        repository = Repository.objects.get(id=repo_id)
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_commit_quality()
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return _error_response('Error retrieving commit quality metrics', exc=e)


@login_required
@require_http_methods(["GET"])
def api_repository_commit_types(request, repo_id):
    """API endpoint for repository commit type distribution"""
    try:
        repository = Repository.objects.get(id=repo_id)
        
        metrics_service = UnifiedMetricsService('repository', repo_id)
        data = metrics_service.get_commit_type_distribution()
        
        return JsonResponse(data)
        
    except Repository.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Repository not found'}, status=404)
    except Exception as e:
        return _error_response('Error retrieving commit type distribution', exc=e)


@login_required
@staff_required
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
            if Repository.objects.filter(github_id=repository_data['id']).exists():
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
                owner=request.user,  # Keep owner for tracking who added it
                is_indexed=False
            )
            added += 1
        return JsonResponse({'success': True, 'added': added, 'skipped': skipped})
    except Exception as e:
        return _error_response('Error adding repositories', exc=e)


@login_required
def repository_licensing_analysis(request, repo_id):
    """AJAX view for licensing analysis slide-over"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Analyze licensing
        license_service = LicenseAnalysisService(repository.full_name)
        analysis = license_service.analyze_commercial_compatibility()
        
        return JsonResponse({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        logger.error("Error in licensing analysis")
        return _error_response('Internal server error during licensing analysis', exc=e)


@login_required
def repository_llm_license_analysis(request, repo_id):
    """AJAX view for LLM license analysis"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get license analysis first
        license_service = LicenseAnalysisService(repository.full_name)
        analysis = license_service.analyze_commercial_compatibility()
        
        if not analysis['has_sbom']:
            return JsonResponse({
                'success': False,
                'error': 'No SBOM found for this repository'
            })
        
        # Extract unique licenses
        unique_licenses = list(analysis['license_summary'].keys())
        
        if not unique_licenses:
            return JsonResponse({
                'success': False,
                'error': 'No licenses found in SBOM'
            })
        
        # Analyze with LLM
        llm_service = LLMService()
        llm_result = llm_service.analyze_licenses(unique_licenses)
        
        if llm_result['success']:
            # Parse LLM response
            parsed_analysis = llm_service.parse_llm_response(llm_result['analysis'])
            
            return JsonResponse({
                'success': True,
                'licenses': unique_licenses,
                'llm_analysis': parsed_analysis,
                'raw_response': llm_result['analysis']
            })
        else:
            return JsonResponse({
                'success': False,
                'error': llm_result['error']
            })
        
    except Exception as e:
        logger.error("Error in LLM license analysis")
        return _error_response('Internal server error during LLM license analysis', exc=e)


@login_required
def repository_llm_license_verdict(request, repo_id):
    """AJAX view for LLM license verdict"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        logger.info("Starting LLM license verdict for repository %s", repo_id)
        
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get license analysis first
        logger.info("Getting license analysis for %s", repository.full_name)
        license_service = LicenseAnalysisService(repository.full_name)
        analysis = license_service.analyze_commercial_compatibility()
        
        if not analysis['has_sbom']:
            logger.warning("No SBOM found for %s", repository.full_name)
            return JsonResponse({
                'success': False,
                'error': 'No SBOM found for this repository'
            })
        
        # Extract unique licenses
        unique_licenses = list(analysis['license_summary'].keys())
        logger.info("Found %d unique licenses: %s", len(unique_licenses), unique_licenses)
        
        if not unique_licenses:
            logger.warning("No licenses found in SBOM for %s", repository.full_name)
            return JsonResponse({
                'success': False,
                'error': 'No licenses found in SBOM'
            })
        
        # Get LLM verdict
        logger.info("Calling LLM service for verdict")
        llm_service = LLMService()
        verdict = llm_service.get_license_verdict(unique_licenses)
        logger.info("LLM verdict: %s", verdict)
        
        return JsonResponse({
            'success': True,
            'verdict': verdict,
            'analysis': analysis  # For fallback
        })
        
    except Exception as e:
        logger.exception("Error in LLM license verdict for repo %s", repo_id)
        return _error_response('Internal server error during LLM license verdict', exc=e)


@login_required
def repository_vulnerabilities_analysis(request, repo_id):
    """AJAX view for vulnerabilities analysis"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get date parameters (for consistency with other APIs)
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Get SBOM analysis
        from analytics.sbom_service import SBOMService
        sbom_service = SBOMService(repository.full_name, request.user.id)
        
        # Check if SBOM exists
        sbom = sbom_service.get_sbom()
        if not sbom:
            return JsonResponse({
                'status': 'no_sbom',
                'message': 'No SBOM found for this repository. Generate one first.'
            })
        
        # Apply date filtering to SBOM generation date
        if start_date and end_date:
            try:
                from django.utils import timezone
                start_dt = timezone.make_aware(datetime.strptime(start_date, "%Y-%m-%d"))
                end_dt = timezone.make_aware(datetime.strptime(end_date, "%Y-%m-%d"))
                # Add one day to end_date to include the full day
                end_dt = end_dt + timedelta(days=1)
                
                # Check if SBOM was generated within the date range
                if sbom.generated_at:
                    sbom_date = sbom.generated_at
                    # Ensure SBOM date is timezone-aware
                    if sbom_date.tzinfo is None:
                        sbom_date = timezone.make_aware(sbom_date)
                    if sbom_date < start_dt or sbom_date >= end_dt:
                        return JsonResponse({
                            'status': 'no_vulnerabilities_in_range',
                            'message': f'No vulnerability data available for the selected period ({start_date} to {end_date}). The latest SBOM was generated on {sbom.generated_at.strftime("%Y-%m-%d")}.'
                        })
            except ValueError:
                # Invalid date format, continue without filtering
                pass
        
        # Get vulnerabilities
        vulnerabilities = sbom_service.get_vulnerabilities()
        
        # Calculate severity counts
        severity_counts = {}
        for vuln in vulnerabilities:
            severity = vuln.get('severity', 'unknown').lower()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # Add date filter info for consistency
        filters = {}
        if start_date and end_date:
            filters['start_date'] = start_date
            filters['end_date'] = end_date
        elif start_date:
            filters['start_date'] = start_date
        elif end_date:
            filters['end_date'] = end_date
        
        # Deprecated: vulnerabilities now come from CodeQL; return empty list with SBOM metadata
        return JsonResponse({
            'status': 'success',
            'vulnerabilities': [],
            'total_vulnerabilities': 0,
            'severity_counts': {},
            'sbom_generated': sbom.generated_at.isoformat() if (sbom and sbom.generated_at) else None,
            'filters': filters,
            'note': 'Dependency vulnerabilities removed; CodeQL provides vulnerabilities now'
        })
        
    except Exception as e:
        logger.exception("Error in vulnerabilities analysis")
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error'
        }, status=500)


@login_required
def repository_commits_list(request, repo_id):
    """AJAX view for commits list with pagination and date filtering"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Get date range parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Import analytics models
        from analytics.models import Commit
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        # Build query
        assert_safe_repository_full_name(repository.full_name)
        commits_query = Commit.objects.filter(repository_full_name=repository.full_name)
        
        # Apply date filtering
        if start_date and end_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to end_date to include the full day
                end_dt = end_dt + timedelta(days=1)
                
                # Check if this is "All Time" (very old start date)
                is_all_time = start_dt.year < 2010
                
                if not is_all_time:
                    commits_query = commits_query.filter(
                        authored_date__gte=start_dt,
                        authored_date__lt=end_dt
                    )
            except ValueError:
                # Invalid date format, apply default 30 days filter
                pass
        
        # If no date parameters provided, apply default 30 days filter
        if not start_date or not end_date:
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)
            commits_query = commits_query.filter(
                authored_date__gte=start_dt,
                authored_date__lt=end_dt
            )
        
        # Get total count
        total_commits = commits_query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        commits = commits_query.order_by('-authored_date')[offset:offset + per_page]
        
        # Serialize commits
        commits_data = []
        for commit in commits:
            # Get real developer name if available
            author_name = commit.author_name
            author_email = commit.author_email
            
            # Try to find the developer alias by name or email
            if commit.author_name or commit.author_email:
                from analytics.models import DeveloperAlias
                from developers.models import Developer
                
                try:
                    # Try to find by name first (case insensitive)
                    alias = None
                    if commit.author_name:
                        alias = DeveloperAlias.objects.filter(
                            name__iexact=commit.author_name
                        ).first()
                    
                    # If not found by name, try by email
                    if not alias and commit.author_email:
                        alias = DeveloperAlias.objects.filter(
                            email__iexact=commit.author_email
                        ).first()
                    
                    if alias and alias.developer:
                        author_name = alias.developer.primary_name
                        # Keep the original email for display
                except Exception:
                    # If any error occurs, keep the original author name
                    pass
            
            commits_data.append({
                'sha': commit.sha,
                'message': commit.message,
                'author_name': author_name,
                'author_email': author_email,
                'authored_date': commit.authored_date.isoformat() if commit.authored_date else None,
                'committed_date': commit.committed_date.isoformat() if commit.committed_date else None,
                'additions': commit.additions,
                'deletions': commit.deletions,
                'total_changes': commit.total_changes,
                'files_changed': len(commit.files_changed) if commit.files_changed else 0,
                'commit_type': commit.commit_type,
                'url': commit.url,
                'pull_request_number': commit.pull_request_number,
                'pull_request_url': commit.pull_request_url
            })
        
        # Calculate pagination info
        total_pages = (total_commits + per_page - 1) // per_page
        has_next = page < total_pages
        has_previous = page > 1
        
        return JsonResponse({
            'success': True,
            'commits': commits_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_commits': total_commits,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_previous': has_previous,
                'next_page': page + 1 if has_next else None,
                'previous_page': page - 1 if has_previous else None
            },
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except Exception as e:
        logger.exception("Error in commits list")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@login_required
def repository_releases_list(request, repo_id):
    """AJAX view for releases list with pagination and date filtering"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Get date range parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Import analytics models
        from analytics.models import Release
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        # Build query
        assert_safe_repository_full_name(repository.full_name)
        releases_query = Release.objects.filter(repository_full_name=repository.full_name)
        
        # Apply date filtering
        if start_date and end_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to end_date to include the full day
                end_dt = end_dt + timedelta(days=1)
                
                # Check if this is "All Time" (very old start date)
                is_all_time = start_dt.year < 2010
                
                if not is_all_time:
                    releases_query = releases_query.filter(
                        published_at__gte=start_dt,
                        published_at__lt=end_dt
                    )
            except ValueError:
                # Invalid date format, apply default 30 days filter
                pass
        
        # If no date parameters provided, apply default 30 days filter
        if not start_date or not end_date:
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)
            releases_query = releases_query.filter(
                published_at__gte=start_dt,
                published_at__lt=end_dt
            )
        
        # Get total count
        total_releases = releases_query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        releases = releases_query.order_by('-published_at')[offset:offset + per_page]
        
        # Serialize releases
        releases_data = []
        for release in releases:
            # Get real developer name if available
            author_name = release.author
            if release.author:
                from analytics.models import DeveloperAlias
                from developers.models import Developer
                
                # Try to find the developer alias by name (pseudo GitHub) - case insensitive
                try:
                    alias = DeveloperAlias.objects.filter(
                        name__iexact=release.author
                    ).first()
                    
                    if alias and alias.developer:
                        author_name = alias.developer.primary_name
                except Exception:
                    # If any error occurs, keep the original author name
                    pass
            
            releases_data.append({
                'release_id': release.release_id,
                'tag_name': release.tag_name,
                'name': release.name,
                'author': author_name,
                'published_at': release.published_at.isoformat() if release.published_at else None,
                'draft': release.draft,
                'prerelease': release.prerelease,
                'body': release.body or '',
                'html_url': release.html_url,
                'url': release.html_url,
            })
        
        # Calculate pagination info
        total_pages = (total_releases + per_page - 1) // per_page
        has_next = page < total_pages
        has_previous = page > 1
        
        return JsonResponse({
            'success': True,
            'releases': releases_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_releases': total_releases,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_previous': has_previous,
                'next_page': page + 1 if has_next else None,
                'previous_page': page - 1 if has_previous else None
            },
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except Exception as e:
        logger.exception("Error in releases list")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@login_required
def repository_deployments_list(request, repo_id):
    """AJAX view for deployments list with pagination and date filtering"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Get date range parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Import analytics models
        from analytics.models import Deployment
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        # Build query
        assert_safe_repository_full_name(repository.full_name)
        deployments_query = Deployment.objects.filter(repository_full_name=repository.full_name)
        
        # Apply date filtering
        if start_date and end_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to end_date to include the full day
                end_dt = end_dt + timedelta(days=1)
                
                # Check if this is "All Time" (very old start date)
                is_all_time = start_dt.year < 2010
                
                if not is_all_time:
                    deployments_query = deployments_query.filter(
                        created_at__gte=start_dt,
                        created_at__lt=end_dt
                    )
            except ValueError:
                # Invalid date format, apply default 30 days filter
                pass
        
        # If no date parameters provided, apply default 30 days filter
        if not start_date or not end_date:
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)
            deployments_query = deployments_query.filter(
                created_at__gte=start_dt,
                created_at__lt=end_dt
            )
        
        # Get total count
        total_deployments = deployments_query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        deployments = deployments_query.order_by('-created_at')[offset:offset + per_page]
        
        # Serialize deployments
        deployments_data = []
        for deployment in deployments:
            # Get real developer name if available
            creator_name = deployment.creator
            
            # Try to find the developer alias by name
            if deployment.creator:
                from analytics.models import DeveloperAlias
                from developers.models import Developer
                
                try:
                    # Try to find by name (case insensitive)
                    alias = DeveloperAlias.objects.filter(
                        name__iexact=deployment.creator
                    ).first()
                    
                    if alias and alias.developer:
                        creator_name = alias.developer.primary_name
                except Exception:
                    # If any error occurs, keep the original creator name
                    pass
            
            # Determine effective status to display
            latest_status = None
            effective_status = None
            if deployment.statuses:
                try:
                    def _parse_iso(ts_str):
                        if not ts_str:
                            return datetime.min
                        try:
                            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        except Exception:
                            return datetime.min

                    statuses_sorted = sorted(
                        deployment.statuses,
                        key=lambda s: _parse_iso(s.get('created_at') or s.get('updated_at'))
                    )
                    latest_status = statuses_sorted[-1]
                    # Prefer the last terminal outcome if present (error/failure/success)
                    terminal = {'error', 'failure', 'success'}
                    terminal_candidates = [s for s in statuses_sorted if str(s.get('state', '')).lower() in terminal]
                    effective_status = terminal_candidates[-1] if terminal_candidates else latest_status
                except Exception:
                    # Fallback to first element if parsing/sorting fails
                    latest_status = deployment.statuses[0]
                    effective_status = latest_status
            
            deployments_data.append({
                'deployment_id': deployment.deployment_id,
                'environment': deployment.environment,
                'creator': creator_name,
                'created_at': deployment.created_at.isoformat() if deployment.created_at else None,
                'updated_at': deployment.updated_at.isoformat() if deployment.updated_at else None,
                'status': str((effective_status or {}).get('state', 'unknown')).lower(),
                'status_description': (effective_status or {}).get('description', ''),
                'status_count': len(deployment.statuses) if deployment.statuses else 0,
                'url': (effective_status or {}).get('target_url', ''),
            })
        
        # Calculate pagination info
        total_pages = (total_deployments + per_page - 1) // per_page
        has_next = page < total_pages
        has_previous = page > 1
        
        return JsonResponse({
            'success': True,
            'deployments': deployments_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_deployments': total_deployments,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_previous': has_previous,
                'next_page': page + 1 if has_next else None,
                'previous_page': page - 1 if has_previous else None
            },
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            }
        })
        
    except Exception as e:
        logger.exception("Error in deployments list")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def repository_sonarcloud_analysis(request, repo_id):
    """Get SonarCloud analysis content for slide-over"""
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get date range from query parameters
        from_date_str = request.GET.get('from')
        to_date_str = request.GET.get('to')
        
        from_date = None
        to_date = None
        
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
            except ValueError:
                pass
                
        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
            except ValueError:
                pass
        
        # Fetch latest metrics and real temporal analysis from service
        sonar_service = SonarCloudService()
        latest_metrics = sonar_service.get_latest_metrics(repo_id)
        temporal_data = sonar_service.get_temporal_analysis(
            repository_id=repo_id,
            repository_full_name=repository.full_name,
            from_date=from_date,
            to_date=to_date
        )
        
        # Prepare data for template
        current_metrics = {
            'bugs': getattr(latest_metrics, 'bugs', 0),
            'vulnerabilities': getattr(latest_metrics, 'vulnerabilities', 0),
            'code_smells': getattr(latest_metrics, 'code_smells', 0),
            'coverage': getattr(latest_metrics, 'coverage', 0),
            'maintainability_rating': getattr(latest_metrics, 'maintainability_rating', 'N/A'),
            'reliability_rating': getattr(latest_metrics, 'reliability_rating', 'N/A'),
            'security_rating': getattr(latest_metrics, 'security_rating', 'N/A'),
            'quality_gate': getattr(latest_metrics, 'quality_gate', 'N/A')
        }
        
        return render(request, 'repositories/sonarcloud_analysis.html', {
            'repository': repository,
            'temporal_data': temporal_data,
            'current_metrics': current_metrics
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting SonarCloud analysis for repository {repo_id}: {e}")
        
        return render(request, 'repositories/sonarcloud_analysis.html', {
            'error_message': 'Failed to load SonarCloud analysis',
            'error_id': str(uuid.uuid4())
        })


@login_required
def repository_codeql_analysis(request, repo_id):
    """API endpoint for CodeQL analysis slide-over content"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        repository = get_object_or_404(Repository, id=repo_id)
        
        # Get CodeQL indexing service
        indexing_service = get_codeql_indexing_service_for_user(request.user.id)
        
        # Get repository security metrics with SHS
        codeql_metrics = indexing_service.get_repository_security_metrics(repository.full_name, repository.id)
        
        # Get detailed vulnerability data if available
        vulnerabilities = []
        if codeql_metrics['total_vulnerabilities'] > 0:
            try:
                from analytics.models import CodeQLVulnerability
                # Get recent vulnerabilities (limit to 50 for performance)
                vuln_objects = CodeQLVulnerability.objects(
                    repository_full_name=repository.full_name
                ).order_by('-created_at').limit(50)
                
                for vuln in vuln_objects:
                    # Resolve developer name who introduced the vulnerability from commit_sha if available
                    introduced_by = None
                    try:
                        if getattr(vuln, 'commit_sha', None):
                            from analytics.models import Commit, DeveloperAlias
                            # Find commit and resolve alias to developer
                            commit = Commit.objects(sha=vuln.commit_sha).first()
                            if commit:
                                introduced_by = commit.author_name or commit.committer_name
                                # Try developer alias resolution by name then email
                                alias = None
                                if introduced_by:
                                    alias = DeveloperAlias.objects.filter(name__iexact=introduced_by).first()
                                if not alias and commit.author_email:
                                    alias = DeveloperAlias.objects.filter(email__iexact=commit.author_email).first()
                                if alias and getattr(alias, 'developer', None):
                                    introduced_by = alias.developer.primary_name
                    except Exception:
                        introduced_by = None

                    # Resolve developer name who fixed the vulnerability from fixed_commit_sha if available
                    fixed_by = None
                    try:
                        if getattr(vuln, 'fixed_commit_sha', None):
                            from analytics.models import Commit, DeveloperAlias
                            fixed_commit = Commit.objects(sha=vuln.fixed_commit_sha).first()
                            if fixed_commit:
                                fixed_by = fixed_commit.author_name or fixed_commit.committer_name
                                alias = None
                                if fixed_by:
                                    alias = DeveloperAlias.objects.filter(name__iexact=fixed_by).first()
                                if not alias and fixed_commit.author_email:
                                    alias = DeveloperAlias.objects.filter(email__iexact=fixed_commit.author_email).first()
                                if alias and getattr(alias, 'developer', None):
                                    fixed_by = alias.developer.primary_name
                    except Exception:
                        fixed_by = None
                    vulnerabilities.append({
                        'rule_id': vuln.rule_id,
                        'rule_name': vuln.rule_name,
                        'rule_description': getattr(vuln, 'rule_description', None),
                        'message': vuln.message,
                        'severity': vuln.severity,
                        'confidence': vuln.confidence,
                        'state': vuln.state,
                        'file_path': vuln.file_path,
                        'start_line': vuln.start_line,
                        'cwe_id': vuln.cwe_id,
                        'dismissed_reason': vuln.dismissed_reason,
                        'html_url': vuln.html_url,
                        'get_age_days': vuln.get_age_days(),
                        'created_at': vuln.created_at,
                        'introduced_by': introduced_by,
                        'fixed_by': fixed_by
                    })
                    
            except Exception as e:
                logger.warning(f"Could not fetch detailed vulnerability data: {e}")
        
        # Recompute open vulnerability counts to ensure consistency in slide-over
        try:
            from analytics.models import CodeQLVulnerability
            open_qs = CodeQLVulnerability.objects(
                repository_full_name=repository.full_name,
                state='open'
            )
            total_open = open_qs.count()
            severity_counts = {
                'critical': open_qs.filter(severity='critical').count(),
                'high': open_qs.filter(severity='high').count(),
                'medium': open_qs.filter(severity='medium').count(),
                'low': open_qs.filter(severity='low').count(),
            }
            codeql_metrics['total_vulnerabilities'] = total_open
            codeql_metrics['severity_counts'] = severity_counts
        except Exception:
            pass

        # Add status information based on recomputed counts
        if codeql_metrics.get('total_vulnerabilities', 0) == 0 and codeql_metrics.get('latest_analysis') is None:
            codeql_metrics['status'] = 'not_available'
        else:
            codeql_metrics['status'] = 'available'

        # Add repository KLOC
        codeql_metrics['kloc'] = repository.kloc or 0.0
        
        # Add vulnerabilities to metrics
        codeql_metrics['vulnerabilities'] = vulnerabilities

        # Build real trend timeline of OPEN vulnerabilities (last 30 days or filtered range)
        from analytics.codeql_service import CodeQLService
        codeql_service = get_codeql_service_for_user(request.user.id, repository.full_name)
        start_param = request.GET.get('from')
        end_param = request.GET.get('to')
        start_dt = None
        end_dt = None
        try:
            if start_param:
                start_dt = datetime.fromisoformat(start_param)
            if end_param:
                # support YYYY-MM-DD
                end_dt = datetime.fromisoformat(end_param)
        except Exception:
            start_dt = None
            end_dt = None

        if codeql_service:
            timeline = codeql_service.get_open_vulnerabilities_timeline(
                repository.full_name, start_dt, end_dt
            )
        else:
            timeline = {'labels': [], 'series': {'critical': [], 'high': [], 'medium': [], 'low': []}}

        # Ensure JSON strings for safe embedding in data-attributes
        codeql_metrics['trend_labels'] = json.dumps(timeline.get('labels', []))
        series = timeline.get('series', {})
        codeql_metrics['trend_series'] = {
            'critical': json.dumps(series.get('critical', [])),
            'high': json.dumps(series.get('high', [])),
            'medium': json.dumps(series.get('medium', [])),
            'low': json.dumps(series.get('low', [])),
        }
        
        logger.info(f"Retrieved CodeQL analysis for {repository.full_name}: {len(vulnerabilities)} vulnerabilities")
        
        return render(request, 'repositories/codeql_analysis.html', {
            'repository': repository,
            'codeql_data': codeql_metrics
        })
        
    except Exception as e:
        logger.error(f"Error getting CodeQL analysis for repository {repo_id}: {e}")
        
        return render(request, 'repositories/codeql_analysis.html', {
            'repository': repository if 'repository' in locals() else None,
            'codeql_data': {
                'status': 'error',
                'message': 'Failed to load CodeQL analysis',
                'error_id': str(uuid.uuid4()),
                'total_vulnerabilities': 0
            }
        })
