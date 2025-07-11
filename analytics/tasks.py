"""
Django-Q tasks for automated synchronization
"""
import logging
from datetime import datetime, timedelta
from django_q.tasks import async_task, schedule
from django_q.models import Schedule

from .sync_service import SyncService
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
        sync_service = SyncService(user_id)
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
        sync_service = SyncService(user_id)
        results = sync_service.sync_repository(repo_full_name, application_id, sync_type)
        
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
                sync_service = SyncService(token.user_id)
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