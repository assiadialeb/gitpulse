"""
Django-Q tasks for automated synchronization
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from typing import Optional
from django_q.tasks import async_task, schedule
from django_q.models import Schedule

from .git_sync_service import GitSyncService
from .services import RateLimitService
from .github_service import GitHubRateLimitError

# from github.models import GitHubToken  # Deprecated - using django-allauth now
from .services import DeploymentIndexingService
from .services import ReleaseIndexingService
from .github_token_service import GitHubTokenService
from .deployment_indexing_service import DeploymentIndexingService
from .commit_indexing_service import CommitIndexingService
from .pullrequest_indexing_service import PullRequestIndexingService
from .release_indexing_service import ReleaseIndexingService
from analytics.models import IndexingState
from .sanitization import assert_safe_repository_full_name
from .decorators import handle_repository_not_found, handle_indexing_errors, monitor_indexing_performance

logger = logging.getLogger(__name__)





def retry_failed_syncs_task():
    """
    Django-Q task to retry failed synchronizations
    """
    logger.info("Starting retry failed syncs task")
    
    try:
        # Get all users with GitHub tokens from django-allauth
        from allauth.socialaccount.models import SocialApp, SocialToken
        from django.contrib.auth.models import User
        
        github_app = SocialApp.objects.filter(provider='github').first()
        if not github_app:
            logger.error("No GitHub SocialApp found")
            return {'error': 'No GitHub SocialApp configured'}
        
        # Get all users who have GitHub tokens
        social_tokens = SocialToken.objects.filter(app=github_app)
        
        total_results = {
            'users_processed': 0,
            'total_retries_attempted': 0,
            'total_retries_successful': 0,
            'total_retries_failed': 0
        }
        
        for social_token in social_tokens:
            try:
                user_id = social_token.account.user.id
                sync_service = GitSyncService(user_id)
                results = sync_service.retry_failed_syncs()
                
                total_results['users_processed'] += 1
                total_results['total_retries_attempted'] += results['retries_attempted']
                total_results['total_retries_successful'] += results['retries_successful']
                total_results['total_retries_failed'] += results['retries_failed']
                
            except Exception as e:
                logger.error(f"Failed to retry syncs for user {social_token.account.user.id}: {e}")
                continue
        
        logger.info(f"Retry failed syncs completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Retry failed syncs task failed: {e}")
        raise


def daily_sync_task():
    """
    Django-Q task to run daily incremental sync for all repositories
    """
    logger.info("Starting daily sync task")
    
    try:
        # Get all repositories that need syncing
        from repositories.models import Repository
        repositories = Repository.objects.all()
        
        total_results = {
            'repositories_processed': 0,
            'total_commits_new': 0,
            'total_api_calls': 0,
            'errors': []
        }
        
        for repository in repositories:
            try:
                # Schedule async task for each repository
                task_id = async_task(
                    'analytics.tasks.sync_repository_task',
                    repository.full_name, None, repository.owner_id, 'incremental',
                    group=f'daily_sync_{datetime.now(dt_timezone.utc).strftime("%Y%m%d")}',
                    timeout=3600  # 1 hour timeout
                )
                
                logger.info(f"Scheduled sync task {task_id} for repository {repository.full_name}")
                total_results['repositories_processed'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule sync for repository {repository.full_name}: {e}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"Daily sync task completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Daily sync task failed: {e}")
        raise


def weekly_full_sync_task():
    """
    Django-Q task to run weekly full sync for all repositories
    """
    logger.info("Starting weekly full sync task")
    
    try:
        # Get all repositories that need syncing
        from repositories.models import Repository
        repositories = Repository.objects.all()
        
        total_results = {
            'repositories_processed': 0,
            'repositories_scheduled': 0,
            'errors': []
        }
        
        for repository in repositories:
            try:
                # Schedule async task for each repository with delay to avoid rate limits
                delay_minutes = total_results['repositories_scheduled'] * 10  # 10 min delay between repos
                
                task_id = async_task(
                    'analytics.tasks.sync_repository_task',
                    repository.full_name, None, repository.owner_id, 'full',
                    group=f'weekly_sync_{datetime.now(dt_timezone.utc).strftime("%Y%m%d")}',
                    timeout=7200,  # 2 hour timeout for full sync
                                          schedule=datetime.now(dt_timezone.utc) + timedelta(minutes=delay_minutes)
                )
                
                logger.info(f"Scheduled full sync task {task_id} for repository {repository.full_name} with {delay_minutes}min delay")
                total_results['repositories_processed'] += 1
                total_results['repositories_scheduled'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule full sync for repository {repository.full_name}: {e}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"Weekly full sync task completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Weekly full sync task failed: {e}")
        raise


def schedule_sync_tasks():
    """
    Set up scheduled tasks in Django-Q
    This should be called once to create the scheduled tasks
    """
    logger.info("Setting up scheduled sync tasks")
    
    # Clear existing schedules (optional - only run this manually)
    # Schedule.objects.filter(func__startswith='analytics.tasks').delete()
    
    try:
        # Daily incremental sync at 2 AM
        daily_schedule, created = Schedule.objects.get_or_create(
            name='daily_incremental_sync',
            defaults={
                'func': 'analytics.tasks.daily_sync_task',
                'schedule_type': Schedule.DAILY,
                'next_run': datetime.now(dt_timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0),
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created daily incremental sync schedule")
        else:
            logger.info("Daily incremental sync schedule already exists")
        
        # Weekly full sync on Sunday at 3 AM
        weekly_schedule, created = Schedule.objects.get_or_create(
            name='weekly_full_sync',
            defaults={
                'func': 'analytics.tasks.weekly_full_sync_task',
                'schedule_type': Schedule.WEEKLY,
                'next_run': datetime.now(dt_timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0),
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created weekly full sync schedule")
        else:
            logger.info("Weekly full sync schedule already exists")
        
        # Retry failed syncs every 4 hours
        retry_schedule, created = Schedule.objects.get_or_create(
            name='retry_failed_syncs',
            defaults={
                'func': 'analytics.tasks.retry_failed_syncs_task',
                'schedule_type': Schedule.HOURLY,
                'minutes': 4 * 60,  # Every 4 hours
                'next_run': datetime.now(dt_timezone.utc) + timedelta(hours=1),  # Start in 1 hour
                'repeats': -1  # Infinite repeats
            }
        )
        if created:
            logger.info("Created retry failed syncs schedule")
        else:
            logger.info("Retry failed syncs schedule already exists")
        
        logger.info("Scheduled sync tasks setup completed")
        return {
            'daily_schedule_created': created if 'daily_schedule' in locals() else False,
            'weekly_schedule_created': created if 'weekly_schedule' in locals() else False,
            'retry_schedule_created': created if 'retry_schedule' in locals() else False,
        }
        
    except Exception as e:
        logger.error(f"Failed to set up scheduled tasks: {e}")
        raise


# Removed manual_sync_application - it used the deprecated Application model


def manual_indexing_task(repository_id: int, user_id: int):
    """
    Tâche d'indexation manuelle pour un repository spécifique (one-shot)
    
    Args:
        repository_id: ID du repository à indexer
        user_id: ID de l'utilisateur qui lance l'indexation
        
    Returns:
        Résultats de l'indexation
    """
    logger.info(f"Starting manual indexing for repository {repository_id}, user {user_id}")
    
    try:
        # Utiliser la même logique que background_indexing_task mais en mode one-shot
        return background_indexing_task(repository_id, user_id, task_id=f"manual_{repository_id}_{datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        
    except Exception as e:
        logger.error(f"Manual indexing failed for repository {repository_id}: {e}")
        raise


def background_indexing_task(repository_id: int, user_id: int, task_id: Optional[str] = None):
    """
    Background task for indexing with progress tracking
    
    Args:
        repository_id: Repository ID to index
        user_id: User ID who owns the repository
        task_id: Optional task ID for progress tracking
    """
    logger.info(f"Starting background indexing for repository {repository_id}, user {user_id}")
    try:
        # Get repository
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
        except Repository.DoesNotExist:
            logger.error(f"Repository {repository_id} not found")
            return {
                'success': False,
                'error': f"Repository {repository_id} not found",
                'task_id': task_id
            }
        
        # Choose indexing service based on configuration
        from django.conf import settings
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'git_local')
        
        if indexing_service == 'github_api':
            from .sync_service import SyncService
            sync_service = SyncService(user_id)
            logger.info(f"Using GitHub API indexing service for repository {repository.full_name}")
        else:
            from .git_sync_service import GitSyncService
            sync_service = GitSyncService(user_id)
            logger.info(f"Using Git local indexing service for repository {repository.full_name}")
        
        results = {
            'repository_id': repository_id,
            'repository_full_name': repository.full_name,
            'indexing_service': indexing_service,
            'commits_new': 0,
            'commits_updated': 0,
            'api_calls': 0,
            'errors': [],
            'task_id': task_id,
            'started_at': datetime.now(dt_timezone.utc).isoformat()
        }
        
        try:
            logger.info(f"Indexing repository: {repository.full_name}")
            
            # Use clone_url for Git local service, or full_name for GitHub API service
            if indexing_service == 'github_api':
                # GitHub API service doesn't need repo_url
                repo_result = sync_service.sync_repository(
                    repository.full_name,
                    None,  # No application_id needed for repository-based indexing
                    'full'  # Always do full sync for indexing
                )
            else:
                # Git local service needs repo_url
                repo_result = sync_service.sync_repository(
                    repository.full_name,
                    repository.clone_url,
                    None,  # No application_id needed for repository-based indexing
                    'full'  # Always do full sync for indexing
                )
            
            results['commits_new'] = repo_result['commits_new']
            results['commits_updated'] = repo_result['commits_updated']
            
            # Track API calls only for GitHub API service
            if indexing_service == 'github_api':
                results['api_calls'] = repo_result.get('api_calls', 0)
            
            # Update repository indexing status
            repository.is_indexed = True
            repository.last_indexed = timezone.now()
            repository.save()
            
            # Calculate KLOC after successful indexing
            try:
                from .kloc_service import KLOCService
                from .models import RepositoryKLOCHistory
                import tempfile
                import os
                from .sanitization import assert_safe_repo_path
                
                # Get repository path (same as GitService)
                repo_path_unsanitized = os.path.join(tempfile.gettempdir(), f"gitpulse_{repository.full_name.replace('/', '_')}")

                # If no local clone exists, skip quietly (API flow handles KLOC now)
                if not os.path.exists(repo_path_unsanitized):
                    logger.info(f"Repository not cloned at {repo_path_unsanitized}, skipping KLOC calculation (no local clone)")
                else:
                    # Validate path only if it exists
                    try:
                        repo_path_obj = assert_safe_repo_path(repo_path_unsanitized)
                        repo_path = str(repo_path_obj)
                    except Exception as path_err:
                        logger.warning(f"Skipping KLOC: unsafe repository path {repo_path_unsanitized} - {path_err}")
                        repo_path = None
                    
                    if repo_path and os.path.exists(repo_path):
                        logger.info(f"Calculating KLOC for {repository.full_name}")
                        kloc_service = KLOCService()
                        kloc_data = kloc_service.calculate_kloc(repo_path)

                        # Save KLOC history
                        kloc_history = RepositoryKLOCHistory(
                            repository_full_name=repository.full_name,
                            repository_id=repository_id,
                            kloc=kloc_data['kloc'],
                            total_lines=kloc_data['total_lines'],
                            language_breakdown=kloc_data['language_breakdown'],
                            calculated_at=kloc_data['calculated_at'],
                            total_files=len(kloc_data.get('language_breakdown', {})),
                            code_files=sum(1 for ext in kloc_data.get('language_breakdown', {}).values() if ext > 0)
                        )
                        kloc_history.save()

                        logger.info(f"KLOC calculation completed for {repository.full_name}: {kloc_data['kloc']:.2f} KLOC")

                        # Add KLOC info to results
                        results['kloc'] = {
                            'value': kloc_data['kloc'],
                            'total_lines': kloc_data['total_lines'],
                            'languages': len(kloc_data['language_breakdown']),
                            'calculated_at': kloc_data['calculated_at'].isoformat()
                        }
                    else:
                        logger.info(f"Repository not cloned at {repo_path_unsanitized}, skipping KLOC calculation")
                    
            except Exception as kloc_error:
                logger.error(f"Error calculating KLOC for {repository.full_name}: {kloc_error}")
                # Don't fail the entire indexing process if KLOC calculation fails
            
            logger.info(f"Completed indexing for repository {repository.full_name}")
            
        except Exception as e:
            error_msg = f"Failed to index repository {repository.full_name}: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        # Run developer grouping after indexing - DISABLED (using new group_developer_identities_task instead)
        # try:
        #     from .developer_grouping_service import DeveloperGroupingService
        #     grouping_service = DeveloperGroupingService()
        #     grouping_result = grouping_service.auto_group_developers()
        #     logger.info(f"Developer grouping completed: {grouping_result}")
        # except Exception as e:
        #     logger.error(f"Developer grouping failed: {e}")
        #     results['errors'].append(f"Developer grouping failed: {str(e)}")
        
        results['completed_at'] = datetime.now(dt_timezone.utc).isoformat()
        logger.info(f"Background indexing completed for repository {repository_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Background indexing failed for repository {repository_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'task_id': task_id
        } 


def daily_indexing_release():
    """
    Django-Q task to index GitHub releases for all indexed repositories (daily)
    """
    logger.info("Starting daily release indexing task")
    results = {
        'repositories_processed': 0,
        'releases_indexed': 0,
        'errors': []
    }
    try:
        from repositories.models import Repository
        indexed_repositories = Repository.objects.all()
        
        for repo in indexed_repositories:
            try:
                user_id = repo.owner_id
                release_service = ReleaseIndexingService(user_id)
                release_ids = release_service.index_releases(None, repo.full_name)
                results['repositories_processed'] += 1
                results['releases_indexed'] += len(release_ids)
            except Exception as e:
                error_msg = f"Failed to index releases for repo {repo.full_name}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        logger.info(f"Daily release indexing completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Daily release indexing task failed: {e}")
        raise 


# Removed quality_analysis_task - it used the deprecated Application model


def fetch_all_pull_requests_task(max_pages_per_repo=50, max_repos_per_run=None, max_execution_time=1800):
    """
    Tâche Q améliorée : va chercher les PRs FERMÉES pour TOUS les repositories indexés,
    avec une gestion intelligente des limites.
    
    Args:
        max_pages_per_repo: Nombre maximum de pages à traiter par repo (défaut: 50)
        max_repos_per_run: Nombre maximum de repos à traiter par exécution (défaut: None = tous)
        max_execution_time: Temps max d'exécution en secondes (défaut: 30 minutes)
    """
    from repositories.models import Repository
    from analytics.models import PullRequest
    from analytics.github_service import GitHubService
    from analytics.sanitization import assert_safe_repository_full_name
    from analytics.github_token_service import GitHubTokenService
    import dateutil.parser
    from datetime import timezone as dt_timezone, datetime
    import logging
    import time

    logger = logging.getLogger(__name__)
    start_time = time.time()

    results = []
    repos_processed = 0
    total_repos_processed = 0
    total_prs_saved = 0
    
    # Récupérer tous les repositories
    indexed_repositories = Repository.objects.all()
    
    total_repos = indexed_repositories.count()
    logger.info(f"Starting PR fetch task for {total_repos} repositories")
    
    if max_repos_per_run:
        indexed_repositories = indexed_repositories[:max_repos_per_run]
        logger.info(f"Limited to {max_repos_per_run} repositories")
    
    for repo in indexed_repositories:
        if time.time() - start_time > max_execution_time:
            logger.info(f"Reached max execution time ({max_execution_time}s), stopping")
            break
            
        user_id = repo.owner_id
        # Prefer org-specific GitHub App token
        access_token = GitHubTokenService.get_token_for_repository_or_org(repo.full_name) or \
                       GitHubTokenService.get_token_for_repository_access(user_id, repo.full_name)
        if not access_token:
            logger.warning(f"[Repo {repo.full_name}] No GitHub token found for user {user_id}.")
            results.append({'repo': repo.full_name, 'error': 'No GitHub token'})
            continue
            
        gh = GitHubService(access_token)
        repo_name = repo.full_name
        total_repos_processed += 1
        
        try:
            page = 1
            repo_prs_saved = 0
            pages_processed = 0
            
            while page <= max_pages_per_repo and pages_processed < max_pages_per_repo:
                if time.time() - start_time > max_execution_time:
                    logger.info(f"[Repo {repo_name}] Timeout reached, stopping at page {page}")
                    break
                    
                url = f"https://api.github.com/repos/{repo_name}/pulls"
                params = {'state': 'closed', 'per_page': 100, 'page': page}
                
                try:
                    prs, _ = gh._make_request(url, params)
                    pages_processed += 1
                    
                    if not prs or len(prs) == 0:
                        logger.info(f"[Repo {repo_name}] No more PRs, stopping pagination")
                        break
                        
                    logger.info(f"[Repo {repo_name}] Page {page}: {len(prs)} PRs fetched.")
                    
                    for pr in prs:
                        pr_number = pr.get('number')
                        try:
                            
                            # Validate then use the original value
                            assert_safe_repository_full_name(repo_name)
                            obj = PullRequest.objects(
                                application_id=None, 
                                repository_full_name=repo_name, 
                                number=pr_number
                            ).first()
                            
                            if not obj:
                                obj = PullRequest(
                                    application_id=None,
                                    repository_full_name=repo_name,
                                    number=pr_number
                                )
                                
                            obj.title = pr.get('title')
                            obj.author = pr.get('user', {}).get('login')
                            obj.created_at = dateutil.parser.parse(pr.get('created_at')) if pr.get('created_at') else None
                            obj.updated_at = dateutil.parser.parse(pr.get('updated_at')) if pr.get('updated_at') else None
                            obj.closed_at = dateutil.parser.parse(pr.get('closed_at')) if pr.get('closed_at') else None
                            obj.merged_at = dateutil.parser.parse(pr.get('merged_at')) if pr.get('merged_at') else None
                            obj.state = pr.get('state')
                            obj.url = pr.get('html_url')
                            obj.labels = [l['name'] for l in pr.get('labels', [])]
                            obj.payload = pr
                            obj.save()
                            
                            repo_prs_saved += 1
                            total_prs_saved += 1
                            
                        except Exception as e:
                            logger.error(f"[Repo {repo_name}] Error saving PR #{pr_number}: {e}")
                            
                    page += 1
                    
                    # Petit délai pour éviter de surcharger l'API
                    time.sleep(0.1)
                    
                except Exception as e:
                    error_msg = str(e)
                    if "Repository not found or not accessible" in error_msg:
                        logger.warning(f"[Repo {repo_name}] Repository not accessible with current token - skipping")
                        results.append({
                            'repo': repo_name, 
                            'status': 'skipped',
                            'reason': 'Repository not accessible with current token',
                            'pages_processed': 0,
                            'total_saved': 0
                        })
                        break
                    else:
                        logger.error(f"[Repo {repo_name}] Error fetching page {page}: {e}")
                        break
            
            execution_time = time.time() - start_time
            logger.info(f"[Repo {repo_name}] Completed: {repo_prs_saved} PRs saved, {pages_processed} pages processed in {execution_time:.1f}s")
            
            results.append({
                'repo': repo_name, 
                'status': 'ok', 
                'total_saved': repo_prs_saved,
                'pages_processed': pages_processed,
                'execution_time': execution_time
            })
            
            repos_processed += 1
            
        except Exception as e:
            logger.error(f"[Repo {repo_name}] Error: {e}")
            results.append({'repo': repo_name, 'error': str(e)})
    
    total_execution_time = time.time() - start_time
    logger.info(f"Task completed: {repos_processed}/{total_repos} repos processed, {total_prs_saved} PRs saved in {total_execution_time:.1f}s")
    
    return {
        'results': results,
        'repos_processed': repos_processed,
        'total_repos': total_repos,
        'total_prs_saved': total_prs_saved,
        'total_execution_time': total_execution_time,
        'max_pages_per_repo': max_pages_per_repo,
        'max_repos_per_run': max_repos_per_run
    }


def fetch_all_pull_requests_detailed_task(max_pages_per_repo=50, max_repos_per_run=10):
    """
    Tâche Q améliorée : va chercher les PRs avec détails complets via l'API GitHub,
    incluant qui a fait le merge pour détecter les self-merges.
    
    Args:
        max_pages_per_repo: Nombre maximum de pages à traiter par repo (défaut: 50)
        max_repos_per_run: Nombre maximum de repos à traiter par exécution (défaut: 10)
    """
    
    from analytics.models import PullRequest
    from analytics.github_service import GitHubService
    from analytics.github_token_service import GitHubTokenService
    import dateutil.parser
    from datetime import timezone as dt_timezone, datetime
    import logging
    import time

    logger = logging.getLogger(__name__)
    start_time = time.time()
    max_execution_time = 600  # 10 minutes max (plus long car plus d'appels API)

    results = []
    repos_processed = 0
    
    # Get all repositories that need indexing
    from repositories.models import Repository
    repositories = Repository.objects.all()
    
    for repository in repositories:
            if repos_processed >= max_repos_per_run:
                logger.info(f"Reached max repos limit ({max_repos_per_run}), stopping")
                break
                
            if time.time() - start_time > max_execution_time:
                logger.info(f"Reached max execution time ({max_execution_time}s), stopping")
                break
                
            user_id = repository.owner_id
            access_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
            if not access_token:
                logger.warning(f"[Repo {repository.full_name}] No GitHub token found for user {user_id}.")
                results.append({'repo': repository.full_name, 'error': 'No GitHub token'})
                continue
                
            gh = GitHubService(access_token)
            
            repo_name = repository.full_name
            repos_processed += 1
            
            try:
                page = 1
                total_saved = 0
                pages_processed = 0
                
                while page <= max_pages_per_repo and pages_processed < max_pages_per_repo:
                    if time.time() - start_time > max_execution_time:
                        logger.info(f"[Repo {repo_name}] Timeout reached, stopping at page {page}")
                        break
                        
                    url = f"https://api.github.com/repos/{repo_name}/pulls"
                    params = {'state': 'closed', 'per_page': 100, 'page': page}
                    
                    try:
                        prs, _ = gh._make_request(url, params)
                        pages_processed += 1
                        
                        logger.info(f"[Repo {repo_name}] Page {page}: {len(prs)} PRs fetched.")
                        
                        if not prs or len(prs) == 0:
                            logger.info(f"[Repo {repo_name}] No more PRs, stopping pagination")
                            break
                            
                        for pr in prs:
                            pr_number = pr.get('number')
                            try:
                                # Récupérer les détails complets de la PR
                                detailed_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
                                detailed_pr, _ = gh._make_request(detailed_url)
                                
                                if detailed_pr:
                                    # Utiliser les données détaillées au lieu des données de base
                                    pr = detailed_pr
                                
                                
                                obj = PullRequest.objects(
                                    application_id=None, 
                                    repository_full_name=assert_safe_repository_full_name(repo_name), 
                                    number=pr_number
                                ).first()
                                
                                if not obj:
                                    obj = PullRequest(
                                        application_id=None,
                                        repository_full_name=assert_safe_repository_full_name(repo_name),
                                        number=pr_number
                                    )
                                    
                                obj.title = pr.get('title')
                                obj.author = pr.get('user', {}).get('login')
                                obj.created_at = dateutil.parser.parse(pr.get('created_at')) if pr.get('created_at') else None
                                obj.updated_at = dateutil.parser.parse(pr.get('updated_at')) if pr.get('updated_at') else None
                                obj.closed_at = dateutil.parser.parse(pr.get('closed_at')) if pr.get('closed_at') else None
                                obj.merged_at = dateutil.parser.parse(pr.get('merged_at')) if pr.get('merged_at') else None
                                obj.state = pr.get('state')
                                obj.url = pr.get('html_url')
                                obj.labels = [l['name'] for l in pr.get('labels', [])]
                                
                                # Ajouter des champs supplémentaires pour les métriques
                                obj.merged_by = pr.get('merged_by', {}).get('login') if pr.get('merged_by') else None
                                obj.requested_reviewers = [r.get('login') for r in pr.get('requested_reviewers', [])]
                                obj.assignees = [a.get('login') for a in pr.get('assignees', [])]
                                obj.review_comments_count = pr.get('review_comments', 0)
                                obj.comments_count = pr.get('comments', 0)
                                obj.commits_count = pr.get('commits', 0)
                                obj.additions_count = pr.get('additions', 0)
                                obj.deletions_count = pr.get('deletions', 0)
                                obj.changed_files_count = pr.get('changed_files', 0)
                                
                                obj.payload = pr
                                obj.save()
                                
                                total_saved += 1
                                
                                # Petit délai pour éviter de surcharger l'API
                                time.sleep(0.1)
                                
                            except Exception as e:
                                logger.error(f"[App {app.id}][Repo {repo_name}] Error saving PR #{pr_number}: {e}")
                                
                        page += 1
                        
                        # Petit délai pour éviter de surcharger l'API
                        time.sleep(0.1)
                        
                    except Exception as e:
                        error_msg = str(e)
                        if "Repository not found or not accessible" in error_msg:
                            logger.warning(f"[App {app.id}][Repo {repo_name}] Repository not accessible with current token - skipping")
                            results.append({
                                'app': app.id, 
                                'repo': repo_name, 
                                'status': 'skipped',
                                'reason': 'Repository not accessible with current token',
                                'pages_processed': 0,
                                'total_saved': 0
                            })
                            break
                        else:
                            logger.error(f"[App {app.id}][Repo {repo_name}] Error fetching page {page}: {e}")
                            break
                
                execution_time = time.time() - start_time
                logger.info(f"[App {app.id}][Repo {repo_name}] Completed: {total_saved} PRs saved, {pages_processed} pages processed in {execution_time:.1f}s")
                
                results.append({
                    'app': app.id, 
                    'repo': repo_name, 
                    'status': 'ok', 
                    'total_saved': total_saved,
                    'pages_processed': pages_processed,
                    'execution_time': execution_time
                })
                
            except Exception as e:
                logger.error(f"[App {app.id}][Repo {repo_name}] Error: {e}")
                results.append({'app': app.id, 'repo': repo_name, 'error': str(e)})
    
    total_execution_time = time.time() - start_time
    logger.info(f"Task completed: {len(results)} repos processed in {total_execution_time:.1f}s")
    
    return {
        'results': results,
        'total_execution_time': total_execution_time,
        'max_pages_per_repo': max_pages_per_repo,
        'max_repos_per_run': max_repos_per_run
    } 


def group_developer_identities_task():
    """
    Tâche Django-Q simplifiée pour regrouper automatiquement les identités de développeurs.
    
    Cette tâche :
    1. Lit tous les commits, PR, releases, deployments
    2. Crée/met à jour les DeveloperAlias avec upsert
    3. Regroupe les aliases avec des règles simples
    4. Crée les Developer avec vérification des doublons
    
    Returns:
        dict: Résultats du regroupement
    """
    import re
    import unicodedata
    from difflib import SequenceMatcher
    from analytics.models import Commit, Developer, DeveloperAlias, PullRequest, Release, Deployment
    
    logger.info("Starting simplified developer identity grouping task")
    
    def normalize_name(name):
        """Normalise un nom : minuscules, sans accents, sans espaces/tirets/underscores"""
        if not name:
            return ""
        # Supprimer les accents
        name = unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode('ascii')
        # Minuscules et supprimer caractères spéciaux
        name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
        return name
    
    def extract_email_local(email):
        """Extrait la partie locale d'un email (avant @)"""
        if not email or '@' not in email:
            return ""
        return email.split('@')[0].lower()
    
    def extract_initials_from_name(name):
        """Extrait les initiales d'un nom complet"""
        if not name:
            return ""
        parts = re.split(r'[^a-zA-Z]+', name.lower())
        return ''.join([part[0] for part in parts if part])
    
    def should_group_identities(identity1, identity2):
        """Détermine si deux identités doivent être regroupées - règles strictes"""
        # Normaliser les emails pour la comparaison
        email1_normalized = identity1['email'].lower()
        email2_normalized = identity2['email'].lower()
        email1_local = extract_email_local(email1_normalized)
        email2_local = extract_email_local(email2_normalized)
        name1_norm = normalize_name(identity1['name'])
        name2_norm = normalize_name(identity2['name'])
        
        # 1. Email identique = Même développeur (confiance 100%)
        if email1_normalized == email2_normalized:
            return True, "exact_email_match"
        
        # 2. Email local identique = Même développeur (confiance 100%)
        if email1_local and email2_local and email1_local == email2_local:
            return True, "email_local_match"
        
        # 3. Patterns d'initiales spécifiques (confiance 85%)
        # Ex: nohemie.lehuby@toto.com ↔ lehuby.nohemie@kisio.com
        # Ex: nlehuby@hove.com ↔ n.lehuby@hove.com
        # Ex: nohemiel@canaltp.fr ↔ nohemie.l@canaltp.fr
        
        if email1_local and email2_local and len(email1_local) > 3 and len(email2_local) > 3:
            # Règle 1: Initiales + nom de famille
            # nohemie.lehuby ↔ lehuby.nohemie
            if '.' in email1_local and '.' in email2_local:
                parts1 = email1_local.split('.')
                parts2 = email2_local.split('.')
                if len(parts1) == 2 and len(parts2) == 2:
                    if (parts1[0] == parts2[1] and parts1[1] == parts2[0]) or \
                       (parts1[0] == parts2[0] and parts1[1] == parts2[1]):
                        return True, "name_reversal_pattern"
            
            # Règle 2: Initiale + nom de famille
            # nlehuby ↔ n.lehuby
            if len(email1_local) > len(email2_local):
                long_email, short_email = email1_local, email2_local
            else:
                long_email, short_email = email2_local, email1_local
            
            if len(short_email) >= 3 and len(long_email) >= len(short_email) + 1:
                # Vérifier si short_email est contenu dans long_email avec un point
                if short_email in long_email.replace('.', ''):
                    return True, "initial_pattern"
        
        return False, None
    
    try:
        # Extraire toutes les identités uniques de toutes les sources
        identities = {}  # key: email, value: {name, email, commit_count, first_seen, last_seen, sources}
        
        logger.info("Processing commits to extract identities")
        
        # 1. Traiter les commits
        for commit in Commit.objects.all():
            # Author
            email = commit.author_email.lower()
            if email not in identities:
                identities[email] = {
                    'name': commit.author_name,
                    'email': email,
                    'commit_count': 0,
                    'first_seen': commit.authored_date,
                    'last_seen': commit.authored_date,
                    'sources': set(['commits'])
                }
            
            identities[email]['commit_count'] += 1
            identities[email]['sources'].add('commits')
            if commit.authored_date < identities[email]['first_seen']:
                identities[email]['first_seen'] = commit.authored_date
            if commit.authored_date > identities[email]['last_seen']:
                identities[email]['last_seen'] = commit.authored_date
            
            # Committer si différent
            if commit.committer_email.lower() != email:
                committer_email = commit.committer_email.lower()
                if committer_email not in identities:
                    identities[committer_email] = {
                        'name': commit.committer_name,
                        'email': committer_email,
                        'commit_count': 0,
                        'first_seen': commit.committed_date,
                        'last_seen': commit.committed_date,
                        'sources': set(['commits'])
                    }
                
                identities[committer_email]['commit_count'] += 1
                identities[committer_email]['sources'].add('commits')
                if commit.committed_date < identities[committer_email]['first_seen']:
                    identities[committer_email]['first_seen'] = commit.committed_date
                if commit.committed_date > identities[committer_email]['last_seen']:
                    identities[committer_email]['last_seen'] = commit.committed_date
        
        # 2. Traiter les Pull Requests
        logger.info("Processing pull requests")
        for pr in PullRequest.objects.all():
            if pr.author:
                email = pr.author.lower()
                if email not in identities:
                    identities[email] = {
                        'name': pr.author,
                        'email': email,
                        'commit_count': 0,
                        'first_seen': pr.created_at or datetime.now(timezone.utc),
                        'last_seen': pr.created_at or datetime.now(timezone.utc),
                        'sources': set(['pull_requests'])
                    }
                else:
                    identities[email]['sources'].add('pull_requests')
                    if pr.created_at and pr.created_at < identities[email]['first_seen']:
                        identities[email]['first_seen'] = pr.created_at
                    if pr.created_at and pr.created_at > identities[email]['last_seen']:
                        identities[email]['last_seen'] = pr.created_at
            
            # Merged by
            if pr.merged_by:
                merged_email = pr.merged_by.lower()
                if merged_email not in identities:
                    identities[merged_email] = {
                        'name': pr.merged_by,
                        'email': merged_email,
                        'commit_count': 0,
                        'first_seen': pr.merged_at or datetime.now(timezone.utc),
                        'last_seen': pr.merged_at or datetime.now(timezone.utc),
                        'sources': set(['pull_requests'])
                    }
                else:
                    identities[merged_email]['sources'].add('pull_requests')
                    if pr.merged_at and pr.merged_at < identities[merged_email]['first_seen']:
                        identities[merged_email]['first_seen'] = pr.merged_at
                    if pr.merged_at and pr.merged_at > identities[merged_email]['last_seen']:
                        identities[merged_email]['last_seen'] = pr.merged_at
        
        # 3. Traiter les Releases
        logger.info("Processing releases")
        for release in Release.objects.all():
            if release.author:
                email = release.author.lower()
                if email not in identities:
                    identities[email] = {
                        'name': release.author,
                        'email': email,
                        'commit_count': 0,
                        'first_seen': release.published_at or datetime.now(timezone.utc),
                        'last_seen': release.published_at or datetime.now(timezone.utc),
                        'sources': set(['releases'])
                    }
                else:
                    identities[email]['sources'].add('releases')
                    if release.published_at and release.published_at < identities[email]['first_seen']:
                        identities[email]['first_seen'] = release.published_at
                    if release.published_at and release.published_at > identities[email]['last_seen']:
                        identities[email]['last_seen'] = release.published_at
        
        # 4. Traiter les Deployments
        logger.info("Processing deployments")
        for deployment in Deployment.objects.all():
            if deployment.creator:
                email = deployment.creator.lower()
                if email not in identities:
                    identities[email] = {
                        'name': deployment.creator,
                        'email': email,
                        'commit_count': 0,
                        'first_seen': deployment.created_at or datetime.now(timezone.utc),
                        'last_seen': deployment.created_at or datetime.now(timezone.utc),
                        'sources': set(['deployments'])
                    }
                else:
                    identities[email]['sources'].add('deployments')
                    if deployment.created_at and deployment.created_at < identities[email]['first_seen']:
                        identities[email]['first_seen'] = deployment.created_at
                    if deployment.created_at and deployment.created_at > identities[email]['last_seen']:
                        identities[email]['last_seen'] = deployment.created_at
        
        logger.info(f"Found {len(identities)} unique identities")
        
        # Créer/mettre à jour les DeveloperAlias avec upsert
        aliases_created = 0
        aliases_updated = 0
        
        for identity_data in identities.values():
            # Chercher l'alias existant ou en créer un nouveau
            alias = DeveloperAlias.objects(email=identity_data['email']).first()
            
            if not alias:
                # Créer un nouvel alias
                alias = DeveloperAlias(
                    email=identity_data['email'],
                    name=identity_data['name'],
                    first_seen=identity_data['first_seen'],
                    last_seen=identity_data['last_seen'],
                    commit_count=identity_data['commit_count']
                )
                alias.save()
                aliases_created += 1
            else:
                # Mettre à jour l'alias existant
                if alias.name != identity_data['name']:
                    # Combiner les noms si différents
                    if identity_data['name'] not in alias.name:
                        alias.name = f"{alias.name} | {identity_data['name']}"
                
                alias.commit_count = identity_data['commit_count']
                alias.first_seen = min(alias.first_seen, identity_data['first_seen'])
                alias.last_seen = max(alias.last_seen, identity_data['last_seen'])
                alias.save()
                aliases_updated += 1
        
        logger.info(f"Created {aliases_created} new aliases, updated {aliases_updated} existing aliases")
        
        # Regroupement simplifié
        ungrouped_aliases = list(DeveloperAlias.objects(developer=None))
        logger.info(f"Processing {len(ungrouped_aliases)} ungrouped aliases for grouping")
        
        developers_created = 0
        aliases_grouped = 0
        grouping_details = []
        
        # Algorithme de regroupement optimisé
        processed_aliases = set()
        
        for i, alias1 in enumerate(ungrouped_aliases):
            if alias1.id in processed_aliases:
                continue
            
            # Créer un nouveau groupe avec cette alias
            group = [alias1]
            identity1 = {'name': alias1.name, 'email': alias1.email}
            
            # Chercher d'autres aliases qui correspondent
            for j, alias2 in enumerate(ungrouped_aliases[i+1:], i+1):
                if alias2.id in processed_aliases:
                    continue
                
                identity2 = {'name': alias2.name, 'email': alias2.email}
                should_group, reason = should_group_identities(identity1, identity2)
                
                if should_group:
                    group.append(alias2)
                    grouping_details.append({
                        'alias1': f"{alias1.name} ({alias1.email})",
                        'alias2': f"{alias2.name} ({alias2.email})",
                        'reason': reason
                    })
            
            # Créer un Developer pour ce groupe
            if len(group) > 0:
                # Choisir l'alias avec le plus de commits comme identité principale
                primary_alias = max(group, key=lambda a: a.commit_count)
                
                # Normaliser l'email pour éviter les doublons (majuscules/minuscules)
                normalized_email = primary_alias.email.lower()
                
                # Vérifier si un Developer avec cet email normalisé existe déjà
                existing_developer = Developer.objects(primary_email__iexact=normalized_email).first()
                
                if existing_developer:
                    # Ajouter les aliases au developer existant
                    for alias in group:
                        if not alias.developer:
                            alias.developer = existing_developer
                            alias.save()
                            processed_aliases.add(alias.id)
                            aliases_grouped += 1
                else:
                    # Créer un nouveau developer avec email normalisé
                    try:
                        developer = Developer(
                            primary_name=primary_alias.name,
                            primary_email=normalized_email,
                            is_auto_grouped=True,
                            confidence_score=min(100, 50 + len(group) * 10)
                        )
                        developer.save()
                        developers_created += 1
                        
                        # Lier toutes les aliases à ce developer
                        for alias in group:
                            alias.developer = developer
                            alias.save()
                            processed_aliases.add(alias.id)
                            aliases_grouped += 1
                    except Exception as e:
                        logger.error(f"Failed to create developer for {normalized_email}: {e}")
                        # En cas d'erreur (doublon), essayer de trouver le developer existant
                        existing_developer = Developer.objects(primary_email__iexact=normalized_email).first()
                        if existing_developer:
                            for alias in group:
                                if not alias.developer:
                                    alias.developer = existing_developer
                                    alias.save()
                                    processed_aliases.add(alias.id)
                                    aliases_grouped += 1
        
        results = {
            'identities_found': len(identities),
            'aliases_created': aliases_created,
            'aliases_updated': aliases_updated,
            'developers_created': developers_created,
            'aliases_grouped': aliases_grouped,
            'grouping_details': grouping_details[:10],
            'total_grouping_details': len(grouping_details)
        }
        
        logger.info(f"Developer identity grouping completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Developer identity grouping task failed: {e}")
        raise



def index_deployments_intelligent_task(repository_id=None, args=None, **kwargs):
    """
    Indexe les déploiements GitHub pour un repository donné, en reprenant là où on s'est arrêté.
    Gère l'état d'indexation (date du dernier déploiement indexé) et les rate limits GitHub.
    """
    # Handle corrupted tasks that pass args as kwargs
    if repository_id is None and args is not None:
        if isinstance(args, list) and len(args) > 0:
            repository_id = args[0]
    
    if repository_id is None:
        raise ValueError("repository_id is required")
    
    # Handle corrupted tasks that pass lists instead of integers
    if isinstance(repository_id, list):
        if len(repository_id) > 0:
            repository_id = repository_id[0]  # Take first element
            if isinstance(repository_id, list) and len(repository_id) > 0:
                repository_id = repository_id[0]  # Handle nested lists
        else:
            raise ValueError("repository_id is an empty list")
    
    # Ensure repository_id is an integer
    try:
        repository_id = int(repository_id)
    except (ValueError, TypeError):
        raise ValueError(f"repository_id must be an integer, got {type(repository_id)}: {repository_id}")
    
    from datetime import timedelta
    from django.utils import timezone
    from repositories.models import Repository
    from analytics.deployment_indexing_service import DeploymentIndexingService
    from analytics.models import IndexingState
    import requests
    import logging
    logger = logging.getLogger(__name__)

    try:
        try:
            repository = Repository.objects.get(id=repository_id)
            assert_safe_repository_full_name(repository.full_name)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping deployment indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        now = timezone.now()
        entity_type = 'deployments'

        # Récupérer ou créer l'état d'indexation
        state = IndexingState.objects(repository_id=repository_id, entity_type=entity_type).first()
        if state and state.last_indexed_at:
            since = state.last_indexed_at
        else:
            # Si pas d'état, on commence il y a 2 ans (ou plus si tu veux)
            # No time limit - index all releases from the beginning
            since = datetime(2010, 1, 1, tzinfo=dt_timezone.utc)  # GitHub was founded in 2008, but use 2010 as safe start
        until = now

        # Récupérer un token GitHub
        from analytics.github_token_service import GitHubTokenService
        # Prefer org integration based on repository owner
        github_token = GitHubTokenService.get_token_for_repository_or_org(repository.full_name)
        if not github_token:
            github_token = GitHubTokenService.get_token_for_repository_access(user_id, repository.full_name) or \
                           GitHubTokenService._get_oauth_app_token()
        if not github_token:
            logger.warning(f"No GitHub token available for repository {repository.full_name}, skipping")
            return {'status': 'skipped', 'reason': 'No GitHub token available', 'repository_id': repository_id}

        # Vérifier la rate limit
        headers = {'Authorization': f'token {github_token}'}
        try:
            rate_response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
            if rate_response.status_code == 200:
                rate_data = rate_response.json()
                remaining = rate_data['resources']['core']['remaining']
                reset_time = rate_data['resources']['core']['reset']
                if remaining < 20:
                    next_run = datetime.fromtimestamp(reset_time, tz=dt_timezone.utc) + timedelta(minutes=5)
                    from django_q.models import Schedule
                    # Check if a retry task already exists for this repository
                    existing_retry = Schedule.objects.filter(
                        name=f'deployment_indexing_repo_{repository_id}_retry'
                    ).first()
                    
                    if existing_retry:
                        # Update existing retry schedule
                        existing_retry.func = 'analytics.tasks.index_deployments_intelligent_task'
                        existing_retry.args = [repository_id]
                        existing_retry.next_run = next_run
                        existing_retry.schedule_type = Schedule.ONCE
                        existing_retry.save()
                    else:
                        # Create new retry schedule
                        Schedule.objects.create(
                            func='analytics.tasks.index_deployments_intelligent_task',
                            args=[repository_id],
                            next_run=next_run,
                            schedule_type=Schedule.ONCE,
                            name=f'deployment_indexing_repo_{repository_id}_retry'
                        )
                    logger.warning(f"Rate limit reached, replanified for {next_run}")
                    return {'status': 'rate_limited', 'scheduled_for': next_run.isoformat()}
        except Exception as e:
            logger.warning(f"Could not check rate limit: {e}, proceeding anyway")

        # Extraire owner et repo depuis full_name
        owner, repo = repository.full_name.split('/', 1)

        # Indexer les déploiements
        deployments = DeploymentIndexingService.fetch_deployments_from_github(
            owner=owner,
            repo=repo,
            token=github_token,
            since=since,
            until=until
        )
        processed = DeploymentIndexingService.process_deployments(deployments)

        # Mettre à jour l'état d'indexation
        if not state:
            state = IndexingState(
                repository_id=repository_id, 
                entity_type=entity_type,
                repository_full_name=repository.full_name
            )
        state.last_indexed_at = until
        state.status = 'completed'
        state.save()

        logger.info(f"Indexed {processed} deployments for {repository.full_name} from {since} to {until}")
        return {
            'status': 'success',
            'processed': processed,
            'repository_id': repository_id,
            'repository_full_name': repository.full_name,
            'date_range': {'since': since.isoformat(), 'until': until.isoformat()}
        }
    except Exception as e:
        logger.error(f"Deployment indexing failed for repository {repository_id}: {e}")
        raise


def index_all_deployments_task():
    """
    Django-Q task to start deployment indexing for all repositories
    """
    logger.info("Starting deployment indexing for all repositories")
    
    try:
        from repositories.models import Repository
        
        results = []
        indexed_repos = Repository.objects.all()  # Index ALL repositories, not just already indexed ones
        
        for repo in indexed_repos:
            try:
                # Start deployment indexing for this repository using v2
                task_id = async_task(
                    'analytics.tasks.index_deployments_intelligent_task',
                    repo.id  # Pass as positional argument
                )
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': task_id,
                    'status': 'scheduled'
                })
                logger.info(f"Scheduled deployment indexing for repository {repo.full_name}")
                
            except Exception as e:
                logger.warning(f"Failed to schedule deployment indexing for repository {repo.full_name}: {e}")
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        summary = {
            'total_repositories': len(indexed_repos),
            'successfully_scheduled': len([r for r in results if r['status'] == 'scheduled']),
            'failed_to_schedule': len([r for r in results if r['status'] == 'failed']),
            'results': results
        }
        
        logger.info(f"Deployment indexing scheduling completed: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to start deployment indexing for all repositories: {e}")
        raise


def index_commits_intelligent_task(repository_id):
    """
    Django-Q task for intelligent commit indexing with PR links
    
    Args:
        repository_id: Repository ID to index (integer or list containing integer)
    """
    # Handle corrupted tasks that pass lists
    if isinstance(repository_id, list):
        repository_id = repository_id[0]
        if isinstance(repository_id, list):
            repository_id = repository_id[0]
    
    repository_id = int(repository_id)
    
    logger.info(f"Starting intelligent commit indexing for repository {repository_id}")
    
    try:
        # Get repository to get user_id
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping commit indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Choose indexing service based on configuration
        from django.conf import settings
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'github_api')
        
        if indexing_service == 'git_local':
            # Use Git local service for commits (NO rate limits, NO pagination, FULL backfill)
            logger.info(f"Using Git local indexing service for FULL BACKFILL of repository {repository.full_name}")
            from .git_sync_service import GitSyncService
            sync_service = GitSyncService(user_id)
            
            # Check if we should skip (simple time-based check instead of complex state)
            from .models import Commit
            
            # Always do a full sync - no artificial limits since constraints are now correct
            # Use FULL sync to get ALL commits in one go (no artificial batching)
            # Always do FULL sync to ensure we have ALL commits from the entire repository history
            result = sync_service.sync_repository(
                repository.full_name,
                repository.clone_url,
                None,  # No application_id needed for repository-based indexing
                'full'  # FULL sync - get ALL commits, no date restrictions, no time limits
            )
            
            # Convert GitSyncService result format to match expected format
            result = {
                'status': 'success',
                'repository_id': repository_id,
                'repository_full_name': repository.full_name,
                'indexing_service': 'git_local',
                'commits_processed': result.get('commits_new', 0) + result.get('commits_updated', 0),
                'commits_new': result.get('commits_new', 0),
                'commits_updated': result.get('commits_updated', 0),
                'has_more': False,  # Git local processes ALL commits at once - no batching needed
                'backfill_complete': True,  # Full backfill completed in one shot
                'errors': result.get('errors', [])
            }
        else:
            # Use GitHub API service for commits
            logger.info(f"Using GitHub API indexing service for commits in repository {repository.full_name}")
            # Use adaptive batch sizing (None triggers adaptive mode)
            batch_size_days = None
            
            # Run intelligent indexing via API
            result = CommitIndexingService.index_commits_for_repository(
                repository_id=repository_id,
                user_id=user_id,
                batch_size_days=batch_size_days
            )
        
        # If there's more to index, schedule the next batch
        if result.get('has_more', False) and result.get('status') == 'success':
            logger.info(f"Scheduling next commit indexing batch for repository {repository_id}")
            # Schedule next run in 1 minute to allow for API rate limiting
            next_run = timezone.now() + timedelta(minutes=1)
            
            from django_q.models import Schedule
            # Check if a task already exists for this repository
            existing_schedule = Schedule.objects.filter(
                name=f'commit_indexing_repo_{repository_id}'
            ).first()
            
            if existing_schedule:
                # Update existing schedule instead of creating a new one
                existing_schedule.func = 'analytics.tasks.index_commits_intelligent_task'
                existing_schedule.args = [repository_id]
                existing_schedule.next_run = next_run
                existing_schedule.schedule_type = Schedule.ONCE
                existing_schedule.save()
                logger.info(f"Updated existing commit indexing schedule for repository {repository_id}")
            else:
                # Create new schedule only if none exists
                Schedule.objects.create(
                    func='analytics.tasks.index_commits_intelligent_task',
                    args=[repository_id],
                    next_run=next_run,
                    schedule_type=Schedule.ONCE,
                    name=f'commit_indexing_repo_{repository_id}'
                )
                logger.info(f"Created new commit indexing schedule for repository {repository_id}")
        else:
            # No more batches -> perform KLOC calculation by cloning the repo locally
            # OR if KLOC is missing or older than 30 days
            should_calculate_kloc = True
            kloc_reason = "backfill_complete"
            
            # Check if KLOC needs recalculation using MongoDB history
            should_calculate_kloc, kloc_reason = repository.should_calculate_kloc(max_days=30)
            if not should_calculate_kloc:
                logger.info(f"KLOC for {repository.full_name} is recent, skipping recalculation: {kloc_reason}")
            
            if should_calculate_kloc:
                try:
                    logger.info(f"----------Starting KLOC calculation ({kloc_reason}) for {repository.full_name}")
                    # Resolve a token suitable for cloning (GitHub App if configured, else user/public)
                    from .github_token_service import GitHubTokenService
                    token = GitHubTokenService.get_token_for_repository_access(user_id, repository.full_name)

                    # Clone repository
                    from .git_service import GitService
                    git_service = GitService()
                    repo_path = git_service.clone_repository(repository.clone_url, repository.full_name, token, repository.default_branch)
                    logger.info(f"----------Cloned repository for KLOC: {repository.full_name} at {repo_path}")

                    # Validate safe repo path before KLOC
                    from .sanitization import assert_safe_repo_path
                    try:
                        safe_repo_path = str(assert_safe_repo_path(repo_path))
                    except Exception as safe_err:
                        logger.warning(f"Skipping KLOC, repo path not safe: {repo_path} - {safe_err}")
                        safe_repo_path = None

                    # Calculate KLOC
                    from .kloc_service import KLOCService
                    kloc_data = KLOCService.calculate_kloc(safe_repo_path or repo_path)

                    # Save KLOC history in Mongo
                    try:
                        from .models import RepositoryKLOCHistory
                        kloc_history = RepositoryKLOCHistory(
                            repository_full_name=repository.full_name,
                            repository_id=repository_id,
                            kloc=kloc_data.get('kloc', 0.0),
                            total_lines=kloc_data.get('total_lines', 0),
                            language_breakdown=kloc_data.get('language_breakdown', {}),
                            calculated_at=kloc_data.get('calculated_at'),
                            total_files=len(kloc_data.get('language_breakdown', {})),
                            code_files=sum(1 for ext_lines in kloc_data.get('language_breakdown', {}).values() if ext_lines > 0)
                        )
                        kloc_history.save()
                    except Exception as mongo_err:
                        logger.warning(f"Failed to save KLOC history for {repository.full_name}: {mongo_err}")

                    # Enrich result payload
                    result['kloc'] = {
                        'value': kloc_data.get('kloc', 0.0),
                        'total_lines': kloc_data.get('total_lines', 0),
                        'languages': len(kloc_data.get('language_breakdown', {})),
                        'calculated_at': (kloc_data.get('calculated_at') or datetime.now(dt_timezone.utc)).isoformat(),
                        'reason': kloc_reason
                    }

                    logger.info(f"KLOC calculation completed ({kloc_reason}) for {repository.full_name}: {kloc_data.get('kloc', 0.0):.2f} KLOC")
                except Exception as kloc_err:
                    logger.warning(f"KLOC calculation skipped/failed for {repository.full_name}: {kloc_err}")
            else:
                logger.info(f"Skipping KLOC calculation for {repository.full_name} - not needed")
        
        # Always mark repository as indexed after processing
        print(f"DEBUG: Marking repository {repository.full_name} as indexed (intelligent task)")
        repository.is_indexed = True
        repository.save()
        logger.info(f"Repository {repository.full_name} marked as indexed")
        result['is_indexed_updated'] = True
        
        logger.info(f"Commit indexing completed for repository {repository_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Commit indexing task failed for repository {repository_id}: {e}")
        raise


def index_commits_git_local_task(repository_id):
    """
    Django-Q task for Git local commit indexing (no state management needed)
    
    Args:
        repository_id: Repository ID to index
    """
    # Handle corrupted tasks that pass lists
    if isinstance(repository_id, list):
        repository_id = repository_id[0]
        if isinstance(repository_id, list):
            repository_id = repository_id[0]
    
    repository_id = int(repository_id)
    
    logger.info(f"Starting Git local commit indexing for repository {repository_id}")
    
    try:
        print(f"DEBUG: Starting git_local task for repository {repository_id}")
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
            print(f"DEBUG: Repository: {repository.full_name}, User: {user_id}")
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping git local commit indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Simple time-based check to avoid too frequent syncing
        from .models import Commit
        from django.utils import timezone
        from datetime import timedelta
        
        # Always do a full sync - no artificial limits since constraints are now correct
        print(f"DEBUG: About to start GitSyncService for {repository.full_name}")
        logger.info(f"Using Git local indexing service for FULL BACKFILL of repository {repository.full_name}")
        from .git_sync_service import GitSyncService
        sync_service = GitSyncService(user_id)
        print(f"DEBUG: GitSyncService created")
        
        # Use FULL sync to get ALL commits in one go
        # Always do FULL sync to ensure we have ALL commits from the entire repository history
        try:
            result = sync_service.sync_repository(
                repository.full_name,
                repository.clone_url,
                None,  # No application_id needed for repository-based indexing
                'full'  # FULL sync - get ALL commits, no date restrictions, no time limits
            )
        except Exception as sync_error:
            # Handle specific sync errors gracefully
            error_msg = str(sync_error).lower()
            
            # Clean up the cloned repository even on error
            try:
                sync_service.cleanup()
                logger.info(f"Cleaned up cloned repository for {repository.full_name} after error")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup cloned repository for {repository.full_name} after error: {cleanup_error}")
            
            if 'repository not found' in error_msg or 'private' in error_msg:
                logger.warning(f"Repository {repository.full_name} is private or not found - skipping")
                return {
                    'status': 'skipped',
                    'reason': 'Repository not found or private',
                    'repository_id': repository_id,
                    'repository_full_name': repository.full_name,
                    'indexing_service': 'git_local',
                    'error': str(sync_error)
                }
            elif 'authentication failed' in error_msg:
                logger.warning(f"Authentication failed for {repository.full_name} - skipping")
                return {
                    'status': 'skipped',
                    'reason': 'Authentication failed',
                    'repository_id': repository_id,
                    'repository_full_name': repository.full_name,
                    'indexing_service': 'git_local',
                    'error': str(sync_error)
                }
            elif 'git pack corruption' in error_msg or 'tmp_pack' in error_msg:
                logger.warning(f"Git pack corruption for {repository.full_name} (possibly LFS) - skipping")
                return {
                    'status': 'skipped',
                    'reason': 'Git pack corruption (possibly LFS or large files)',
                    'repository_id': repository_id,
                    'repository_full_name': repository.full_name,
                    'indexing_service': 'git_local',
                    'error': str(sync_error)
                }
            else:
                # Re-raise other errors
                raise
        
        # Convert result format
        final_result = {
            'status': 'success',
            'repository_id': repository_id,
            'repository_full_name': repository.full_name,
            'indexing_service': 'git_local',
            'commits_processed': result.get('commits_new', 0) + result.get('commits_updated', 0),
            'commits_new': result.get('commits_new', 0),
            'commits_updated': result.get('commits_updated', 0),
            'has_more': False,  # Git local processes ALL commits at once
            'backfill_complete': True,  # Full backfill completed
            'errors': result.get('errors', [])
        }
        
        # Calculate KLOC for git_local mode (since we have the repository cloned)
        # OR if KLOC is missing or older than 30 days
        should_calculate_kloc = True
        kloc_reason = "git_local_backfill"
        
        # Check if KLOC needs recalculation using MongoDB history
        should_calculate_kloc, kloc_reason = repository.should_calculate_kloc(max_days=30)
        if not should_calculate_kloc:
            logger.info(f"KLOC for {repository.full_name} is recent, skipping recalculation: {kloc_reason}")
        
        if should_calculate_kloc:
            try:
                logger.info(f"----------Starting KLOC calculation ({kloc_reason}) for {repository.full_name}")
                
                # Get the cloned repository path
                repo_path = sync_service.get_repo_path(repository.full_name)
                
                # Validate safe repo path before KLOC
                from .sanitization import assert_safe_repo_path
                try:
                    safe_repo_path = str(assert_safe_repo_path(repo_path))
                except Exception as safe_err:
                    logger.warning(f"Skipping KLOC, repo path not safe: {repo_path} - {safe_err}")
                    safe_repo_path = None

                # Calculate KLOC
                from .kloc_service import KLOCService
                kloc_data = KLOCService.calculate_kloc(safe_repo_path or repo_path)

                # Save KLOC history in Mongo
                try:
                    from .models import RepositoryKLOCHistory
                    kloc_history = RepositoryKLOCHistory(
                        repository_full_name=repository.full_name,
                        repository_id=repository_id,
                        kloc=kloc_data.get('kloc', 0.0),
                        total_lines=kloc_data.get('total_lines', 0),
                        language_breakdown=kloc_data.get('language_breakdown', {}),
                        calculated_at=kloc_data.get('calculated_at'),
                        total_files=len(kloc_data.get('language_breakdown', {})),
                        code_files=sum(1 for ext_lines in kloc_data.get('language_breakdown', {}).values() if ext_lines > 0)
                    )
                    kloc_history.save()
                except Exception as mongo_err:
                    logger.warning(f"Failed to save KLOC history for {repository.full_name}: {mongo_err}")

                # Add KLOC info to results
                final_result['kloc'] = {
                    'value': kloc_data.get('kloc', 0.0),
                    'total_lines': kloc_data.get('total_lines', 0),
                    'languages': len(kloc_data.get('language_breakdown', {})),
                    'calculated_at': (kloc_data.get('calculated_at') or datetime.now(dt_timezone.utc)).isoformat(),
                    'reason': kloc_reason
                }

                logger.info(f"KLOC calculation completed ({kloc_reason}) for {repository.full_name}: {kloc_data.get('kloc', 0.0):.2f} KLOC")
            except Exception as kloc_err:
                logger.warning(f"KLOC calculation skipped/failed for {repository.full_name}: {kloc_err}")
        else:
            logger.info(f"Skipping KLOC calculation for {repository.full_name} - not needed")
        
        # Always mark repository as indexed after processing (success or not)
        print(f"DEBUG: Marking repository {repository.full_name} as indexed")
        repository.is_indexed = True
        repository.save()
        logger.info(f"Repository {repository.full_name} marked as indexed")
        final_result['is_indexed_updated'] = True
        
        # Clean up the cloned repository after indexing is complete
        try:
            sync_service.cleanup()
            logger.info(f"Successfully cleaned up cloned repository for {repository.full_name}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup cloned repository for {repository.full_name}: {cleanup_error}")
            final_result['cleanup_error'] = str(cleanup_error)
        
        logger.info(f"Git local commit indexing completed for repository {repository_id}: {final_result}")
        return final_result
        
    except Exception as e:
        logger.error(f"Git local commit indexing failed for repository {repository_id}: {e}")
        
        # Clean up the cloned repository even on unexpected errors
        try:
            if 'sync_service' in locals():
                sync_service.cleanup()
                logger.info(f"Cleaned up cloned repository for repository {repository_id} after unexpected error")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup cloned repository for repository {repository_id} after unexpected error: {cleanup_error}")
        
        return {
            'status': 'failed',
            'reason': f'Unexpected error: {str(e)}',
            'repository_id': repository_id,
            'repository_full_name': getattr(repository, 'full_name', 'unknown') if 'repository' in locals() else 'unknown',
            'indexing_service': 'git_local',
            'error': str(e)
        }


def index_all_commits_task():
    """
    Django-Q task to start commit indexing for all repositories
    """
    logger.info("Starting commit indexing for all repositories")
    
    try:
        from repositories.models import Repository
        
        results = []
        indexed_repos = Repository.objects.all()  # Index ALL repositories, not just already indexed ones
        
        for repo in indexed_repos:
            try:
                # Choose the right task based on INDEXING_SERVICE setting
                from django.conf import settings
                indexing_service = getattr(settings, 'INDEXING_SERVICE', 'github_api')
                
                if indexing_service == 'git_local':
                    # Use dedicated git_local task (no state management)
                    task_function = 'analytics.tasks.index_commits_git_local_task'
                else:
                    # Use intelligent task with state management for GitHub API
                    task_function = 'analytics.tasks.index_commits_intelligent_task'
                
                # Start commit indexing for this repository
                task_id = async_task(task_function, repo.id)
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': task_id,
                    'status': 'scheduled'
                })
                logger.info(f"Scheduled commit indexing for repository {repo.full_name}")
                
            except Exception as e:
                logger.warning(f"Failed to schedule commit indexing for repository {repo.full_name}: {e}")
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        summary = {
            'total_repositories': len(indexed_repos),
            'successfully_scheduled': len([r for r in results if r['status'] == 'scheduled']),
            'failed_to_schedule': len([r for r in results if r['status'] == 'failed']),
            'results': results
        }
        
        logger.info(f"Commit indexing scheduling completed: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to start commit indexing for all repositories: {e}")
        raise


def index_pullrequests_intelligent_task(repository_id=None, args=None, **kwargs):
    """
    Django-Q task for intelligent pull request indexing
    
    Args:
        repository_id: Repository ID to index pull requests for
        args: Alternative way to pass arguments (for corrupted tasks)
    """
    # Handle corrupted tasks that pass args as kwargs
    if repository_id is None and args is not None:
        if isinstance(args, list) and len(args) > 0:
            repository_id = args[0]
    
    if repository_id is None:
        raise ValueError("repository_id is required")
    
    # Handle corrupted tasks that pass lists instead of integers
    if isinstance(repository_id, list):
        if len(repository_id) > 0:
            repository_id = repository_id[0]  # Take first element
            if isinstance(repository_id, list) and len(repository_id) > 0:
                repository_id = repository_id[0]  # Handle nested lists
        else:
            raise ValueError("repository_id is an empty list")
    
    # Ensure repository_id is an integer
    try:
        repository_id = int(repository_id)
    except (ValueError, TypeError):
        raise ValueError(f"repository_id must be an integer, got {type(repository_id)}: {repository_id}")
    
    logger.info(f"Starting intelligent pull request indexing for repository {repository_id}")
    
    try:
        # Get repository to get user_id
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping pull request indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Intelligent rate limit check before proceeding
        from .github_token_service import GitHubTokenService
        import requests
        
        # Get token for rate limit check
        github_token = (
            GitHubTokenService.get_token_for_repository_or_org(repository.full_name)
            or GitHubTokenService.get_token_for_repository_access(user_id, repository.full_name)
            or GitHubTokenService._get_oauth_app_token()
        )
        
        if github_token:
            # Check rate limit
            headers = {'Authorization': f'token {github_token}'}
            try:
                rate_response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
                
                if rate_response.status_code == 200:
                    rate_data = rate_response.json()
                    remaining = rate_data['resources']['core']['remaining']
                    
                    # If rate limited, schedule for later
                    if remaining < 50:  # Keep buffer for PR indexing (needs multiple requests)
                        logger.warning(f"GitHub API rate limit low ({remaining} remaining), scheduling PR indexing for later")
                        
                        # Schedule next run after rate limit reset
                        reset_time = datetime.fromtimestamp(rate_data['resources']['core']['reset'])
                        next_run = reset_time + timedelta(minutes=5)  # 5 minutes after reset
                        
                        from django_q.models import Schedule
                        Schedule.objects.create(
                            func='analytics.tasks.index_pullrequests_intelligent_task',
                            args=[repository_id],
                            next_run=next_run,
                            schedule_type=Schedule.ONCE,
                            name=f'pullrequest_indexing_repo_{repository_id}_retry'
                        )
                        
                        return {
                            'status': 'rate_limited',
                            'repository_id': repository_id,
                            'repository_full_name': repository.full_name,
                            'remaining_requests': remaining,
                            'scheduled_for': next_run.isoformat(),
                            'message': f'Scheduled for retry at {next_run}'
                        }
                        
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding with indexing")
        
        batch_size_days = 30  # Default batch size
        
        # Run intelligent indexing
        result = PullRequestIndexingService.index_pullrequests_for_repository(
            repository_id=repository_id,
            user_id=user_id,
            batch_size_days=batch_size_days
        )
        
        # If there's more to index, schedule the next batch
        if result.get('has_more', False) and result.get('status') == 'success':
            logger.info(f"Scheduling next pull request indexing batch for repository {repository_id}")
            # Schedule next run in 3 minutes to allow for API rate limiting
            next_run = timezone.now() + timedelta(minutes=3)
            
            from django_q.models import Schedule
            # Check if a task already exists for this repository
            existing_schedule = Schedule.objects.filter(
                name=f'pullrequest_indexing_repo_{repository_id}'
            ).first()
            
            if existing_schedule:
                # Update existing schedule instead of creating a new one
                existing_schedule.func = 'analytics.tasks.index_pullrequests_intelligent_task'
                existing_schedule.args = [repository_id]
                existing_schedule.next_run = next_run
                existing_schedule.schedule_type = Schedule.ONCE
                existing_schedule.save()
                logger.info(f"Updated existing pull request indexing schedule for repository {repository_id}")
            else:
                # Create new schedule only if none exists
                Schedule.objects.create(
                    func='analytics.tasks.index_pullrequests_intelligent_task',
                    args=[repository_id],
                    next_run=next_run,
                    schedule_type=Schedule.ONCE,
                    name=f'pullrequest_indexing_repo_{repository_id}'
                )
                logger.info(f"Created new pull request indexing schedule for repository {repository_id}")
        
        logger.info(f"Pull request indexing completed for repository {repository_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Pull request indexing task failed for repository {repository_id}: {e}")
        raise


def index_all_pullrequests_task():
    """
    Django-Q task to start pull request indexing for all repositories
    """
    logger.info("Starting pull request indexing for all repositories")
    
    try:
        from repositories.models import Repository
        
        results = []
        indexed_repos = Repository.objects.all()  # Index ALL repositories, not just already indexed ones
        
        for repo in indexed_repos:
            try:
                # Start pull request indexing for this repository
                task_id = async_task(
                    'analytics.tasks.index_pullrequests_intelligent_task',
                    repo.id  # Pass as positional argument
                )
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': task_id,
                    'status': 'scheduled'
                })
                logger.info(f"Scheduled pull request indexing for repository {repo.full_name}")
                
            except Exception as e:
                logger.warning(f"Failed to schedule pull request indexing for repository {repo.full_name}: {e}")
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        summary = {
            'total_repositories': len(indexed_repos),
            'successfully_scheduled': len([r for r in results if r['status'] == 'scheduled']),
            'failed_to_schedule': len([r for r in results if r['status'] == 'failed']),
            'results': results
        }
        
        logger.info(f"Pull request indexing scheduling completed: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to start pull request indexing for all repositories: {e}")
        raise


def index_releases_intelligent_task(repository_id=None, args=None, **kwargs):
    """
    Django-Q task for intelligent release indexing
    
    Args:
        repository_id: Repository ID to index releases for
        args: Alternative way to pass arguments (for corrupted tasks)
    """
    # Handle corrupted tasks that pass args as kwargs
    if repository_id is None and args is not None:
        if isinstance(args, list) and len(args) > 0:
            repository_id = args[0]
    
    if repository_id is None:
        raise ValueError("repository_id is required")
    
    # Handle corrupted tasks that pass lists instead of integers
    if isinstance(repository_id, list):
        if len(repository_id) > 0:
            repository_id = repository_id[0]  # Take first element
            if isinstance(repository_id, list) and len(repository_id) > 0:
                repository_id = repository_id[0]  # Handle nested lists
        else:
            raise ValueError("repository_id is an empty list")
    
    # Ensure repository_id is an integer
    try:
        repository_id = int(repository_id)
    except (ValueError, TypeError):
        raise ValueError(f"repository_id must be an integer, got {type(repository_id)}: {repository_id}")
    
    logger.info(f"Starting intelligent release indexing for repository {repository_id}")
    
    try:
        # Get repository to get user_id
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping release indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Intelligent rate limit check before proceeding
        from .github_token_service import GitHubTokenService
        import requests
        
        # Get token for rate limit check
        github_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
        if not github_token:
            github_token = GitHubTokenService._get_user_token(user_id)
            if not github_token:
                github_token = GitHubTokenService._get_oauth_app_token()
        
        if github_token:
            # Check rate limit
            headers = {'Authorization': f'token {github_token}'}
            try:
                rate_response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
                
                if rate_response.status_code == 200:
                    rate_data = rate_response.json()
                    remaining = rate_data['resources']['core']['remaining']
                    
                    # If rate limited, schedule for later
                    if remaining < 20:  # Releases need fewer requests than PRs
                        logger.warning(f"GitHub API rate limit low ({remaining} remaining), scheduling release indexing for later")
                        
                        # Schedule next run after rate limit reset
                        reset_time = datetime.fromtimestamp(rate_data['resources']['core']['reset'])
                        next_run = reset_time + timedelta(minutes=10)  # 10 minutes after reset
                        
                        from django_q.models import Schedule
                        # Check if a retry task already exists for this repository
                        existing_retry = Schedule.objects.filter(
                            name=f'release_indexing_repo_{repository_id}_retry'
                        ).first()
                        
                        if existing_retry:
                            # Update existing retry schedule
                            existing_retry.func = 'analytics.tasks.index_releases_intelligent_task'
                            existing_retry.args = [repository_id]
                            existing_retry.next_run = next_run
                            existing_retry.schedule_type = Schedule.ONCE
                            existing_retry.save()
                        else:
                            # Create new retry schedule
                            Schedule.objects.create(
                                func='analytics.tasks.index_releases_intelligent_task',
                                args=[repository_id],
                                next_run=next_run,
                                schedule_type=Schedule.ONCE,
                                name=f'release_indexing_repo_{repository_id}_retry'
                            )
                        
                        return {
                            'status': 'rate_limited',
                            'repository_id': repository_id,
                            'repository_full_name': repository.full_name,
                            'remaining_requests': remaining,
                            'scheduled_for': next_run.isoformat(),
                            'message': f'Scheduled for retry at {next_run}'
                        }
                        
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding with indexing")
        
        batch_size_days = 90  # Default batch size
        
        # Run intelligent indexing
        result = ReleaseIndexingService.index_releases_for_repository(
            repository_id=repository_id,
            user_id=user_id,
            batch_size_days=batch_size_days
        )
        
        # If there's more to index, schedule the next batch
        if result.get('has_more', False) and result.get('status') == 'success':
            logger.info(f"Scheduling next release indexing batch for repository {repository_id}")
            # Schedule next run in 5 minutes to allow for API rate limiting
            next_run = timezone.now() + timedelta(minutes=5)
            
            from django_q.models import Schedule
            # Check if a task already exists for this repository
            existing_schedule = Schedule.objects.filter(
                name=f'release_indexing_repo_{repository_id}'
            ).first()
            
            if existing_schedule:
                # Update existing schedule instead of creating a new one
                existing_schedule.func = 'analytics.tasks.index_releases_intelligent_task'
                existing_schedule.args = [repository_id]
                existing_schedule.next_run = next_run
                existing_schedule.schedule_type = Schedule.ONCE
                existing_schedule.save()
                logger.info(f"Updated existing release indexing schedule for repository {repository_id}")
            else:
                # Create new schedule only if none exists
                Schedule.objects.create(
                    func='analytics.tasks.index_releases_intelligent_task',
                    args=[repository_id],
                    next_run=next_run,
                    schedule_type=Schedule.ONCE,
                    name=f'release_indexing_repo_{repository_id}'
                )
                logger.info(f"Created new release indexing schedule for repository {repository_id}")
        
        logger.info(f"Release indexing completed for repository {repository_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Release indexing task failed for repository {repository_id}: {e}")
        raise


def index_all_releases_task():
    """
    Django-Q task to start release indexing for all repositories
    """
    logger.info("Starting release indexing for all repositories")
    
    try:
        from repositories.models import Repository
        
        results = []
        indexed_repos = Repository.objects.all()  # Index ALL repositories, not just already indexed ones
        
        for repo in indexed_repos:
            try:
                # Start release indexing for this repository
                task_id = async_task(
                    'analytics.tasks.index_releases_intelligent_task',
                    repo.id  # Pass as positional argument
                )
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': task_id,
                    'status': 'scheduled'
                })
                logger.info(f"Scheduled release indexing for repository {repo.full_name}")
                
            except Exception as e:
                logger.warning(f"Failed to schedule release indexing for repository {repo.full_name}: {e}")
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        summary = {
            'total_repositories': len(indexed_repos),
            'successfully_scheduled': len([r for r in results if r['status'] == 'scheduled']),
            'failed_to_schedule': len([r for r in results if r['status'] == 'failed']),
            'results': results
        }
        
        logger.info(f"Release indexing scheduling completed: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to start release indexing for all repositories: {e}")
        raise


def generate_sbom_task(repository_id: int, force_generate: bool = False):
    """
    Django-Q task to generate SBOM for a repository
    
    Args:
        repository_id: Repository ID to generate SBOM for
        force_generate: Force generation even if SBOM exists
    """
    logger.info(f"Starting SBOM generation for repository {repository_id}")
    
    try:
        from repositories.models import Repository
        from .models import SBOM
        from .sbom_service import SBOMService
        
        # Get repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping SBOM generation")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Check if SBOM already exists (unless forced)
        if not force_generate:
            # Validate before querying
            assert_safe_repository_full_name(repository.full_name)
            existing_sbom = SBOM.objects(repository_full_name=repository.full_name).first()
            if existing_sbom:
                logger.info(f"SBOM already exists for {repository.full_name}, skipping")
                return {
                    'status': 'skipped',
                    'reason': 'SBOM already exists',
                    'repository_id': repository_id
                }
        
        # Fetch SBOM via GitHub API (SPDX preferred)
        sbom_service = SBOMService(repository.full_name, user_id)
        sbom_doc = sbom_service.fetch_github_sbom(user_id)
        if isinstance(sbom_doc, dict) and ('spdxVersion' in sbom_doc or sbom_doc.get('SPDXID')):
            # SPDX from GitHub Dependency Graph
            sbom = sbom_service.process_spdx_sbom(sbom_doc)
        else:
            # Assume CycloneDX-compatible document
            sbom = sbom_service.process_sbom(sbom_doc)
        
        logger.info(f"Successfully generated SBOM for {repository.full_name}")
        return {
            'status': 'success',
            'repository_id': repository_id,
            'repository_full_name': repository.full_name,
            'sbom_id': str(sbom.id),
            'component_count': sbom.component_count,
            'vulnerability_count': 0
        }
        
    except Exception as e:
        logger.error(f"SBOM generation failed for repository {repository_id}: {e}")
        raise


def check_new_releases_and_generate_sbom_task():
    """
    Django-Q task to check for new releases and generate SBOM if needed
    """
    logger.info("Starting new release SBOM generation check")
    
    try:
        from repositories.models import Repository
        from .models import Release, SBOM
        from django.utils import timezone
        from datetime import timedelta
        
        results = {
            'repositories_checked': 0,
            'sboms_generated': 0,
            'errors': []
        }
        
        # Get all indexed repositories
        repositories = Repository.objects.filter(is_indexed=True)
        
        for repo in repositories:
            try:
                results['repositories_checked'] += 1
                
                # Check if repository has any SBOM
                assert_safe_repository_full_name(repo.full_name)
                existing_sbom = SBOM.objects(repository_full_name=repo.full_name).first()
                
                # Check for new releases in the last 24 hours
                assert_safe_repository_full_name(repo.full_name)
                recent_releases = Release.objects(
                    repository_full_name=repo.full_name,
                    published_at__gte=timezone.now() - timedelta(days=1)
                ).count()
                
                # Generate SBOM if:
                # 1. No SBOM exists for this repository, OR
                # 2. New releases were published in the last 24 hours
                should_generate = not existing_sbom or recent_releases > 0
                
                if should_generate:
                    logger.info(f"Generating SBOM for {repo.full_name} "
                              f"(existing_sbom: {bool(existing_sbom)}, "
                              f"recent_releases: {recent_releases})")
                    
                    # Schedule SBOM generation task
                    from django_q.tasks import async_task
                    async_task('analytics.tasks.generate_sbom_task', repo.id)
                    
                    results['sboms_generated'] += 1
                else:
                    logger.info(f"No SBOM generation needed for {repo.full_name}")
                    
            except Exception as e:
                error_msg = f"Error processing repository {repo.full_name}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        logger.info(f"SBOM generation check completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"SBOM generation check failed: {e}")
        raise


def index_codeql_intelligent_task(repository_id=None, args=None, **kwargs):
    """
    Django-Q task for intelligent CodeQL vulnerability indexing
    
    Args:
        repository_id: Repository ID to index CodeQL alerts for
        args: Alternative way to pass arguments (for corrupted tasks)
    """
    # Handle corrupted tasks that pass args as kwargs
    if repository_id is None and args is not None:
        if isinstance(args, list) and len(args) > 0:
            repository_id = args[0]
    
    if repository_id is None:
        raise ValueError("repository_id is required")
    
    # Handle corrupted tasks that pass lists instead of integers
    if isinstance(repository_id, list):
        if len(repository_id) > 0:
            repository_id = repository_id[0]  # Take first element
            if isinstance(repository_id, list) and len(repository_id) > 0:
                repository_id = repository_id[0]  # Handle nested lists
        else:
            raise ValueError("repository_id is an empty list")
    
    # Ensure repository_id is an integer
    try:
        repository_id = int(repository_id)
    except (ValueError, TypeError):
        raise ValueError(f"repository_id must be an integer, got {type(repository_id)}: {repository_id}")
    
    logger.info(f"Starting intelligent CodeQL indexing for repository {repository_id}")
    
    try:
        # Get repository to get user_id
        from repositories.models import Repository
        try:
            repository = Repository.objects.get(id=repository_id)
            user_id = repository.owner.id
        except Repository.DoesNotExist:
            logger.warning(f"Repository {repository_id} no longer exists, skipping CodeQL indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        
        # Intelligent rate limit check before proceeding
        from .github_token_service import GitHubTokenService
        import requests
        
        # Get token for rate limit check
        github_token = GitHubTokenService.get_token_for_operation('code_scanning', user_id)
        if not github_token:
            github_token = GitHubTokenService._get_user_token(user_id)
            if not github_token:
                github_token = GitHubTokenService._get_oauth_app_token()
        
        if github_token:
            # Check rate limit
            headers = {'Authorization': f'token {github_token}'}
            try:
                rate_response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
                
                if rate_response.status_code == 200:
                    rate_data = rate_response.json()
                    remaining = rate_data['resources']['core']['remaining']
                    
                    # If rate limited, schedule for later
                    if remaining < 30:  # Keep buffer for CodeQL API calls
                        logger.warning(f"GitHub API rate limit low ({remaining} remaining), scheduling CodeQL indexing for later")
                        
                        # Schedule next run after rate limit reset
                        reset_time = datetime.fromtimestamp(rate_data['resources']['core']['reset'])
                        next_run = reset_time + timedelta(minutes=10)  # 10 minutes after reset
                        
                        from django_q.models import Schedule
                        # Check if a retry task already exists for this repository
                        existing_retry = Schedule.objects.filter(
                            name=f'codeql_indexing_repo_{repository_id}_retry'
                        ).first()
                        
                        if existing_retry:
                            # Update existing retry schedule
                            existing_retry.func = 'analytics.tasks.index_codeql_intelligent_task'
                            existing_retry.args = [repository_id]
                            existing_retry.next_run = next_run
                            existing_retry.schedule_type = Schedule.ONCE
                            existing_retry.save()
                        else:
                            # Create new retry schedule
                            Schedule.objects.create(
                                func='analytics.tasks.index_codeql_intelligent_task',
                                args=[repository_id],
                                next_run=next_run,
                                schedule_type=Schedule.ONCE,
                                name=f'codeql_indexing_repo_{repository_id}_retry'
                            )
                        
                        return {
                            'status': 'rate_limited',
                            'repository_id': repository_id,
                            'repository_full_name': repository.full_name,
                            'remaining_requests': remaining,
                            'scheduled_for': next_run.isoformat(),
                            'message': f'Scheduled for retry at {next_run}'
                        }
                        
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding with indexing")
        
        # Run intelligent indexing
        from .codeql_indexing_service import get_codeql_indexing_service_for_user
        indexing_service = get_codeql_indexing_service_for_user(user_id)
        
        result = indexing_service.index_codeql_for_repository(
            repository_id=repository_id,
            repository_full_name=repository.full_name
        )
        
        logger.info(f"CodeQL indexing completed for repository {repository_id}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"CodeQL indexing task failed for repository {repository_id}: {e}")
        raise


def index_all_codeql_task():
    """
    Django-Q task to start CodeQL indexing for all repositories
    """
    logger.info("Starting CodeQL indexing for all repositories")
    
    try:
        from repositories.models import Repository
        
        results = []
        repositories = Repository.objects.all()  # Index ALL repositories, not just already indexed ones
        
        for repo in repositories:
            try:
                # Start CodeQL indexing for this repository
                task_id = async_task(
                    'analytics.tasks.index_codeql_intelligent_task',
                    repo.id  # Pass as positional argument
                )
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': task_id,
                    'status': 'scheduled'
                })
                logger.info(f"Scheduled CodeQL indexing for repository {repo.full_name}")
                
            except Exception as e:
                logger.warning(f"Failed to schedule CodeQL indexing for repository {repo.full_name}: {e}")
                results.append({
                    'repo_id': repo.id,
                    'repo_name': repo.full_name,
                    'task_id': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        summary = {
            'total_repositories': len(repositories),
            'successfully_scheduled': len([r for r in results if r['status'] == 'scheduled']),
            'failed_to_schedule': len([r for r in results if r['status'] == 'failed']),
            'results': results
        }
        
        logger.info(f"CodeQL indexing scheduling completed: {summary}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to start CodeQL indexing for all repositories: {e}")
        raise


def daily_codeql_analysis_task():
    """
    Django-Q task to run daily CodeQL analysis for all indexed repositories
    """
    logger.info("Starting daily CodeQL analysis task")
    
    try:
        from repositories.models import Repository
        
        results = {
            'repositories_processed': 0,
            'vulnerabilities_found': 0,
            'errors': []
        }
        
        # Get all indexed repositories
        indexed_repositories = Repository.objects.filter(is_indexed=True)
        
        for repo in indexed_repositories:
            try:
                user_id = repo.owner_id
                from .codeql_indexing_service import get_codeql_indexing_service_for_user
                
                indexing_service = get_codeql_indexing_service_for_user(user_id)
                
                # Only reindex if needed (not forced)
                if indexing_service.should_reindex(repo.full_name):
                    # Schedule async task for this repository
                    task_id = async_task(
                        'analytics.tasks.index_codeql_intelligent_task',
                        repo.id,
                        group=f'daily_codeql_{datetime.now(dt_timezone.utc).strftime("%Y%m%d")}',
                        timeout=1800  # 30 minute timeout
                    )
                    
                    logger.info(f"Scheduled CodeQL analysis task {task_id} for repository {repo.full_name}")
                    results['repositories_processed'] += 1
                else:
                    logger.info(f"Skipping CodeQL analysis for {repo.full_name} - recently analyzed")
                
            except Exception as e:
                error_msg = f"Failed to schedule CodeQL analysis for repository {repo.full_name}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        logger.info(f"Daily CodeQL analysis task completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Daily CodeQL analysis task failed: {e}")
        raise


def cleanup_old_tasks_task():
    """
    Django-Q task to clean up old completed tasks
    """
    logger.info("Starting cleanup of old completed tasks")
    
    try:
        # Delete tasks older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        old_tasks = Task.objects.filter(
            success=True,
            stopped__lt=cutoff_date
        )
        
        count = old_tasks.count()
        old_tasks.delete()
        
        logger.info(f"Cleaned up {count} old completed tasks")
        return {'cleaned_count': count}
        
    except Exception as e:
        logger.error(f"Cleanup old tasks failed: {e}")
        raise


def cleanup_stuck_indexing_task():
    """
    Django-Q task to clean up stuck indexing operations
    """
    logger.info("Starting cleanup of stuck indexing operations")
    
    try:
        from .monitoring_service import IndexingMonitoringService
        cleaned_count = IndexingMonitoringService.cleanup_stuck_indexing()
        
        logger.info(f"Cleaned up {cleaned_count} stuck indexing operations")
        return {'cleaned_count': cleaned_count}
        
    except Exception as e:
        logger.error(f"Cleanup stuck indexing failed: {e}")
        raise


def monitoring_health_check_task():
    """
    Django-Q task to run health check and generate alerts
    """
    logger.info("Starting indexing health check")
    
    try:
        from .monitoring_service import IndexingMonitoringService
        health_report = IndexingMonitoringService.get_indexing_health_report()
        
        # Log alerts
        for alert in health_report.get('alerts', []):
            if alert['level'] == 'warning':
                logger.warning(f"Indexing alert: {alert['message']}")
            elif alert['level'] == 'error':
                logger.error(f"Indexing alert: {alert['message']}")
        
        logger.info(f"Health check completed: {health_report['overview']['successful_tasks_1h']} successful, {health_report['overview']['failed_tasks_1h']} failed")
        return health_report
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise


