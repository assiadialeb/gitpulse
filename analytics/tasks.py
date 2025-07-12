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
        
        # Initialize sync service
        sync_service = GitSyncService(user_id)
        
        results = {
            'application_id': application_id,
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
                
                repo_result = sync_service.sync_repository(
                    app_repo.github_repo_name,
                    repo_url,
                    application_id,
                    'full'  # Always do full sync for indexing
                )
                
                # Check if rate limit was hit
                if repo_result.get('rate_limit_hit'):
                    logger.warning(f"Rate limit hit during indexing of {app_repo.github_repo_name}")
                    
                    # Get user's GitHub username for rate limit service
                    try:
                        github_token = GitHubToken.objects.get(user_id=user_id)
                        github_username = github_token.github_username
                    except GitHubToken.DoesNotExist:
                        github_username = f"user_{user_id}"
                    
                    # Handle rate limit with automatic restart
                    task_data = {
                        'application_id': application_id,
                        'user_id': user_id,
                        'task_id': task_id
                    }
                    
                    # Create a rate limit error for handling
                    rate_limit_error = GitHubRateLimitError("Rate limit exceeded during indexing")
                    
                    restart_info = RateLimitService.handle_rate_limit_error(
                        user_id=user_id,
                        github_username=github_username,
                        error=rate_limit_error,
                        task_type='indexing',
                        task_data=task_data,
                        original_task_id=task_id
                    )
                    
                    # Return restart information
                    results['rate_limit_hit'] = True
                    results['restart_info'] = restart_info
                    results['completed_at'] = datetime.utcnow().isoformat()
                    results['success'] = False
                    
                    logger.info(f"Rate limit hit during indexing. Restart scheduled: {restart_info}")
                    return results
                
                results['repositories_synced'] += 1
                results['total_commits_new'] += repo_result['commits_new']
                results['total_commits_updated'] += repo_result['commits_updated']
                # Git local doesn't use API calls, so we don't track them
                results['total_api_calls'] = 0
                
                logger.info(f"Completed {i}/{total_repos} repositories")
                
            except Exception as e:
                error_msg = f"Failed to index repository {app_repo.github_repo_name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        results['completed_at'] = datetime.utcnow().isoformat()
        results['success'] = True
        
        logger.info(f"Background indexing completed for application {application_id}: {results}")
        return results
        
    except Exception as e:
        error_msg = f"Background indexing failed for application {application_id}: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'task_id': task_id
        } 