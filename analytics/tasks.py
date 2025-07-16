"""
Django-Q tasks for automated synchronization
"""
import logging
from datetime import datetime, timedelta
from django_q.tasks import async_task, schedule
from django_q.models import Schedule

from .git_sync_service import GitSyncService
from .services import RateLimitService
from .github_service import GitHubRateLimitError
from applications.models import Application, ApplicationRepository
from github.models import GitHubToken
from .services import DeploymentIndexingService
from .services import ReleaseIndexingService

logger = logging.getLogger(__name__)


def sync_application_task(application_id: int, user_id: int, sync_type: str = 'incremental'):
    """
    Django-Q task to sync all repositories for an application
    
    Args:
        application_id: Application ID to sync
        user_id: User ID who owns the application
        sync_type: 'full' or 'incremental'
    """
    logger.info(f"Starting sync task for application {application_id}, user {user_id}")
    
    try:
        sync_service = GitSyncService(user_id)
        results = sync_service.sync_application_repositories(application_id, sync_type)
        
        logger.info(f"Sync completed for application {application_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Sync task failed for application {application_id}: {e}")
        raise


def sync_repository_task(repo_full_name: str, application_id: int, user_id: int, 
                        sync_type: str = 'incremental'):
    """
    Django-Q task to sync a specific repository
    
    Args:
        repo_full_name: Repository name in format "owner/repo"
        application_id: Application ID
        user_id: User ID who owns the application
        sync_type: 'full' or 'incremental'
    """
    logger.info(f"Starting sync task for repository {repo_full_name}")
    
    try:
        sync_service = GitSyncService(user_id)
        # On a besoin de l'URL du repo pour GitSyncService, on la récupère via ApplicationRepository
        from applications.models import ApplicationRepository
        app_repo = ApplicationRepository.objects.get(github_repo_name=repo_full_name, application_id=application_id)
        
        # Check if github_repo_url exists, if not generate it
        repo_url = getattr(app_repo, 'github_repo_url', None)
        if not repo_url:
            repo_url = f"https://github.com/{app_repo.github_repo_name}.git"
            logger.warning(f"Missing github_repo_url for {app_repo.github_repo_name}, using generated URL: {repo_url}")
        
        results = sync_service.sync_repository(repo_full_name, repo_url, application_id, sync_type)
        
        logger.info(f"Sync completed for repository {repo_full_name}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Sync task failed for repository {repo_full_name}: {e}")
        raise


def retry_failed_syncs_task():
    """
    Django-Q task to retry failed synchronizations
    """
    logger.info("Starting retry failed syncs task")
    
    try:
        # Get all users with GitHub tokens
        github_tokens = GitHubToken.objects.all()
        
        total_results = {
            'users_processed': 0,
            'total_retries_attempted': 0,
            'total_retries_successful': 0,
            'total_retries_failed': 0
        }
        
        for token in github_tokens:
            try:
                sync_service = GitSyncService(token.user_id)
                results = sync_service.retry_failed_syncs()
                
                total_results['users_processed'] += 1
                total_results['total_retries_attempted'] += results['retries_attempted']
                total_results['total_retries_successful'] += results['retries_successful']
                total_results['total_retries_failed'] += results['retries_failed']
                
            except Exception as e:
                logger.error(f"Failed to retry syncs for user {token.user_id}: {e}")
                continue
        
        logger.info(f"Retry failed syncs completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Retry failed syncs task failed: {e}")
        raise


def daily_sync_task():
    """
    Django-Q task to run daily incremental sync for all applications
    """
    logger.info("Starting daily sync task")
    
    try:
        # Get all applications that have repositories
        applications_with_repos = Application.objects.filter(
            applicationrepository__isnull=False
        ).distinct()
        
        total_results = {
            'applications_processed': 0,
            'total_repositories_synced': 0,
            'total_commits_new': 0,
            'total_api_calls': 0,
            'errors': []
        }
        
        for application in applications_with_repos:
            try:
                # Schedule async task for each application
                task_id = async_task(
                    'analytics.tasks.sync_application_task',
                    application.id,
                    application.owner_id,
                    'incremental',
                    group=f'daily_sync_{datetime.now().strftime("%Y%m%d")}',
                    timeout=3600  # 1 hour timeout
                )
                
                logger.info(f"Scheduled sync task {task_id} for application {application.id}")
                total_results['applications_processed'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule sync for application {application.id}: {e}"
                logger.error(error_msg)
                total_results['errors'].append(error_msg)
        
        logger.info(f"Daily sync task completed: {total_results}")
        return total_results
        
    except Exception as e:
        logger.error(f"Daily sync task failed: {e}")
        raise


def weekly_full_sync_task():
    """
    Django-Q task to run weekly full sync for all applications
    """
    logger.info("Starting weekly full sync task")
    
    try:
        # Get all applications that have repositories
        applications_with_repos = Application.objects.filter(
            applicationrepository__isnull=False
        ).distinct()
        
        total_results = {
            'applications_processed': 0,
            'applications_scheduled': 0,
            'errors': []
        }
        
        for application in applications_with_repos:
            try:
                # Schedule async task for each application with delay to avoid rate limits
                delay_minutes = total_results['applications_scheduled'] * 10  # 10 min delay between apps
                
                task_id = async_task(
                    'analytics.tasks.sync_application_task',
                    application.id,
                    application.owner_id,
                    'full',
                    group=f'weekly_sync_{datetime.now().strftime("%Y%m%d")}',
                    timeout=7200,  # 2 hour timeout for full sync
                    schedule=datetime.now() + timedelta(minutes=delay_minutes)
                )
                
                logger.info(f"Scheduled full sync task {task_id} for application {application.id} with {delay_minutes}min delay")
                total_results['applications_processed'] += 1
                total_results['applications_scheduled'] += 1
                
            except Exception as e:
                error_msg = f"Failed to schedule full sync for application {application.id}: {e}"
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
                'next_run': datetime.now().replace(hour=2, minute=0, second=0, microsecond=0),
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
                'next_run': datetime.now().replace(hour=3, minute=0, second=0, microsecond=0),
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
                'next_run': datetime.now() + timedelta(hours=1),  # Start in 1 hour
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


def manual_sync_application(application_id: int, sync_type: str = 'incremental'):
    """
    Manually trigger sync for an application (for testing or on-demand sync)
    
    Args:
        application_id: Application ID to sync
        sync_type: 'full' or 'incremental'
        
    Returns:
        Task ID for tracking
    """
    try:
        application = Application.objects.get(id=application_id)
        
        task_id = async_task(
            'analytics.tasks.sync_application_task',
            application_id,
            application.owner_id,
            sync_type,
            group=f'manual_sync_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            timeout=3600
        )
        
        logger.info(f"Manually triggered sync task {task_id} for application {application_id}")
        return task_id
        
    except Application.DoesNotExist:
        raise ValueError(f"Application {application_id} not found")
    except Exception as e:
        logger.error(f"Failed to manually trigger sync for application {application_id}: {e}")
        raise


def background_indexing_task(application_id: int, user_id: int, task_id: str = None):
    """
    Background task for indexing with progress tracking
    
    Args:
        application_id: Application ID to index
        user_id: User ID who owns the application
        task_id: Optional task ID for progress tracking
    """
    logger.info(f"Starting background indexing for application {application_id}, user {user_id}")
    try:
        # Get application and repositories
        application = Application.objects.get(id=application_id, owner_id=user_id)
        repositories = application.repositories.all()
        total_repos = repositories.count()
        
        if total_repos == 0:
            logger.warning(f"No repositories found for application {application_id}")
            return {
                'success': False,
                'error': 'No repositories found for this application',
                'task_id': task_id
            }
        
        # Choose indexing service based on configuration
        from django.conf import settings
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'git_local')
        
        if indexing_service == 'github_api':
            from .sync_service import SyncService
            sync_service = SyncService(user_id)
            logger.info(f"Using GitHub API indexing service for application {application_id}")
        else:
            from .git_sync_service import GitSyncService
            sync_service = GitSyncService(user_id)
            logger.info(f"Using Git local indexing service for application {application_id}")
        
        results = {
            'application_id': application_id,
            'indexing_service': indexing_service,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_api_calls': 0,
            'errors': [],
            'total_repositories': total_repos,
            'task_id': task_id,
            'started_at': datetime.utcnow().isoformat()
        }
        
        # Process each repository
        for i, app_repo in enumerate(repositories, 1):
            try:
                logger.info(f"Indexing repository {i}/{total_repos}: {app_repo.github_repo_name}")
                
                # Check if github_repo_url exists, if not generate it
                repo_url = getattr(app_repo, 'github_repo_url', None)
                if not repo_url:
                    repo_url = f"https://github.com/{app_repo.github_repo_name}.git"
                    logger.warning(f"Missing github_repo_url for {app_repo.github_repo_name}, using generated URL: {repo_url}")
                
                if indexing_service == 'github_api':
                    # GitHub API service doesn't need repo_url
                    repo_result = sync_service.sync_repository(
                        app_repo.github_repo_name,
                        application_id,
                        'full'  # Always do full sync for indexing
                    )
                else:
                    # Git local service needs repo_url
                    repo_result = sync_service.sync_repository(
                        app_repo.github_repo_name,
                        repo_url,
                        application_id,
                        'full'  # Always do full sync for indexing
                    )
                
                results['repositories_synced'] += 1
                results['total_commits_new'] += repo_result['commits_new']
                results['total_commits_updated'] += repo_result['commits_updated']
                
                # Track API calls only for GitHub API service
                if indexing_service == 'github_api':
                    results['total_api_calls'] += repo_result.get('api_calls', 0)
                else:
                    results['total_api_calls'] = 0
                
                logger.info(f"Completed {i}/{total_repos} repositories")
                
            except Exception as e:
                error_msg = f"Failed to index repository {app_repo.github_repo_name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Run developer grouping after indexing
        try:
            from .developer_grouping_service import DeveloperGroupingService
            grouping_service = DeveloperGroupingService()
            grouping_result = grouping_service.auto_group_developers()
            logger.info(f"Developer grouping completed: {grouping_result}")
        except Exception as e:
            logger.error(f"Developer grouping failed: {e}")
            results['errors'].append(f"Developer grouping failed: {str(e)}")
        
        results['completed_at'] = datetime.utcnow().isoformat()
        logger.info(f"Background indexing completed for application {application_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Background indexing failed for application {application_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'task_id': task_id
        } 


def daily_indexing_release():
    """
    Django-Q task to index GitHub releases for all repositories of all applications (daily)
    """
    logger.info("Starting daily release indexing task")
    results = {
        'applications_processed': 0,
        'repositories_processed': 0,
        'releases_indexed': 0,
        'errors': []
    }
    try:
        applications_with_repos = Application.objects.filter(
            repositories__isnull=False
        ).distinct()
        for app in applications_with_repos:
            try:
                user_id = app.owner_id
                release_service = ReleaseIndexingService(user_id)
                repos = app.repositories.all()
                for repo in repos:
                    try:
                        release_ids = release_service.index_releases(app.id, repo.github_repo_name)
                        results['repositories_processed'] += 1
                        results['releases_indexed'] += len(release_ids)
                    except Exception as e:
                        error_msg = f"Failed to index releases for repo {repo.github_repo_name} (app {app.id}): {e}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
                results['applications_processed'] += 1
            except Exception as e:
                error_msg = f"Failed to process application {app.id}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        logger.info(f"Daily release indexing completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Daily release indexing task failed: {e}")
        raise 


def quality_analysis_task(application_id):
    """
    Tâche Q indépendante pour lancer l'analyse de qualité sur tous les commits d'une application.
    """
    from analytics.quality_service import QualityAnalysisService
    return QualityAnalysisService().analyze_commits_for_application(application_id)


def developer_grouping_task(application_id):
    """
    Tâche Q indépendante pour lancer le groupement automatique des développeurs d'une application.
    """
    from analytics.developer_grouping_service import DeveloperGroupingService
    return DeveloperGroupingService(application_id).auto_group_developers() 


def quality_analysis_all_apps_task():
    """
    Tâche Q pour lancer l'analyse de qualité sur toutes les applications.
    """
    from applications.models import Application
    from analytics.quality_service import QualityAnalysisService
    processed = 0
    for app in Application.objects.all():
        processed += QualityAnalysisService().analyze_commits_for_application(app.id)
    return processed


def developer_grouping_all_apps_task():
    """
    Tâche Q pour lancer le groupement automatique des développeurs sur toutes les applications.
    """
    from applications.models import Application
    from analytics.developer_grouping_service import DeveloperGroupingService
    results = []
    for app in Application.objects.all():
        results.append(DeveloperGroupingService(app.id).auto_group_developers())
    return results 


def release_indexing_task(application_id):
    """
    Tâche Q pour indexer les releases de toutes les repositories d'une application.
    """
    from applications.models import Application
    from analytics.services import ReleaseIndexingService
    app = Application.objects.get(id=application_id)
    user_id = app.owner_id
    release_service = ReleaseIndexingService(user_id)
    results = []
    for repo in app.repositories.all():
        results.append(release_service.index_releases(app.id, repo.github_repo_name))
    return results


def release_indexing_all_apps_task():
    """
    Tâche Q pour indexer les releases de toutes les applications et repositories.
    """
    from applications.models import Application
    from analytics.services import ReleaseIndexingService
    results = []
    for app in Application.objects.all():
        user_id = app.owner_id
        release_service = ReleaseIndexingService(user_id)
        for repo in app.repositories.all():
            results.append(release_service.index_releases(app.id, repo.github_repo_name))
    return results 


def fetch_all_pull_requests_task():
    """
    Tâche Q de test : va chercher toutes les PRs FERMÉES pour tous les repos de toutes les applications via l'API GitHub,
    et les stocke dans la collection PullRequest. Traverse toute la pagination jusqu'à ce qu'il n'y ait plus de résultats.
    """
    from applications.models import Application
    from analytics.models import PullRequest
    from analytics.github_service import GitHubService
    from github.models import GitHubToken
    import dateutil.parser
    from datetime import timezone
    import logging

    logger = logging.getLogger(__name__)

    results = []
    for app in Application.objects.all():
        user_id = app.owner_id
        token_obj = GitHubToken.objects.filter(user_id=user_id).first()
        if not token_obj:
            logger.warning(f"[App {app.id}] No GitHub token found.")
            results.append({'app': app.id, 'error': 'No GitHub token'})
            continue
        gh = GitHubService(token_obj.access_token)
        for repo in app.repositories.all():
            repo_name = repo.github_repo_name
            try:
                page = 1
                total_saved = 0
                while True:
                    url = f"https://api.github.com/repos/{repo_name}/pulls"
                    params = {'state': 'closed', 'per_page': 100, 'page': page}
                    prs, _ = gh._make_request(url, params)
                    logger.info(f"[App {app.id}][Repo {repo_name}] Page {page}: {len(prs)} PRs fetched.")
                    if not prs or len(prs) == 0:
                        break
                    for pr in prs:
                        pr_number = pr.get('number')
                        try:
                            obj = PullRequest.objects(application_id=app.id, repository_full_name=repo_name, number=pr_number).first()
                            if not obj:
                                obj = PullRequest(
                                    application_id=app.id,
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
                            logger.info(f"[App {app.id}][Repo {repo_name}] PR #{pr_number} saved.")
                            total_saved += 1
                        except Exception as e:
                            logger.error(f"[App {app.id}][Repo {repo_name}] Error saving PR #{pr_number}: {e}")
                    page += 1
                logger.info(f"[App {app.id}][Repo {repo_name}] Total PRs saved: {total_saved}")
                results.append({'app': app.id, 'repo': repo_name, 'status': 'ok', 'total_saved': total_saved})
            except Exception as e:
                logger.error(f"[App {app.id}][Repo {repo_name}] Error: {e}")
                results.append({'app': app.id, 'repo': repo_name, 'error': str(e)})
    return results 