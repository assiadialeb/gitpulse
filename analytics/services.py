"""
Services for MongoDB cleanup operations
"""
from typing import Dict
from .models import Commit, SyncLog, RepositoryStats


def cleanup_application_data(application_id: int) -> Dict:
    """
    Clean up all MongoDB data related to an application
    
    Args:
        application_id: The ID of the application to clean up
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'commits_deleted': 0,
        'sync_logs_deleted': 0,
        'repository_stats_deleted': 0,
        'quality_metrics_deleted': 0,
        'total_deleted': 0
    }
    
    try:
        # Delete all commits for this application
        commits_deleted = Commit.objects.filter(application_id=application_id).delete()
        results['commits_deleted'] = commits_deleted
        
        # Delete all sync logs for this application
        sync_logs_deleted = SyncLog.objects.filter(application_id=application_id).delete()
        results['sync_logs_deleted'] = sync_logs_deleted
        
        # Delete all repository stats for this application
        repo_stats_deleted = RepositoryStats.objects.filter(application_id=application_id).delete()
        results['repository_stats_deleted'] = repo_stats_deleted
        
        # Delete all quality metrics for this application
        from pymongo import MongoClient
        client = MongoClient('localhost', 27017)
        db = client['gitpulse']
        quality_collection = db['developer_quality_metrics']
        
        # Get repository names for this application to filter quality metrics
        from applications.models import Application
        try:
            application = Application.objects.get(id=application_id)
            repository_names = list(application.repositories.values_list('github_repo_name', flat=True))
            
            if repository_names:
                # Delete quality metrics for repositories in this application
                quality_result = quality_collection.delete_many({
                    'repository': {'$in': repository_names}
                })
                results['quality_metrics_deleted'] = int(quality_result.deleted_count)
            else:
                results['quality_metrics_deleted'] = 0
        except Application.DoesNotExist:
            # Application already deleted, try to delete by application_id if it exists in quality metrics
            quality_result = quality_collection.delete_many({
                'application_id': application_id
            })
            results['quality_metrics_deleted'] = int(quality_result.deleted_count)
        
        client.close()
        
        # Calculate total
        results['total_deleted'] = (
            results['commits_deleted'] + 
            results['sync_logs_deleted'] + 
            results['repository_stats_deleted'] +
            results['quality_metrics_deleted']
        )
        
        return results
        
    except Exception as e:
        # Return error information
        results['error'] = str(e)
        return results


def cleanup_repository_data(repository_full_name: str) -> Dict:
    """
    Clean up all MongoDB data related to a specific repository
    
    Args:
        repository_full_name: The repository name in format "owner/repo"
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'commits_deleted': 0,
        'sync_logs_deleted': 0,
        'repository_stats_deleted': 0,
        'quality_metrics_deleted': 0,
        'total_deleted': 0
    }
    
    try:
        # Delete all commits for this repository
        commits_deleted = Commit.objects.filter(repository_full_name=repository_full_name).delete()
        results['commits_deleted'] = commits_deleted
        
        # Delete all sync logs for this repository
        sync_logs_deleted = SyncLog.objects.filter(repository_full_name=repository_full_name).delete()
        results['sync_logs_deleted'] = sync_logs_deleted
        
        # Delete repository stats for this repository
        repo_stats_deleted = RepositoryStats.objects.filter(repository_full_name=repository_full_name).delete()
        results['repository_stats_deleted'] = repo_stats_deleted
        
        # Delete quality metrics for this repository
        from pymongo import MongoClient
        client = MongoClient('localhost', 27017)
        db = client['gitpulse']
        quality_collection = db['developer_quality_metrics']
        
        quality_result = quality_collection.delete_many({
            'repository': repository_full_name
        })
        results['quality_metrics_deleted'] = int(quality_result.deleted_count)
        
        client.close()
        
        # Calculate total
        results['total_deleted'] = (
            results['commits_deleted'] + 
            results['sync_logs_deleted'] + 
            results['repository_stats_deleted'] +
            results['quality_metrics_deleted']
        )
        
        return results
        
    except Exception as e:
        # Return error information
        results['error'] = str(e)
        return results

"""
Rate limit management service for handling GitHub API rate limits
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from django_q.tasks import async_task, Schedule
from django_q.models import Schedule as ScheduleModel

from .github_service import GitHubRateLimitError
# from github.models import GitHubToken  # Deprecated - using PAT now

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for managing GitHub API rate limits and automatic task restarts"""
    
    @staticmethod
    def handle_rate_limit_error(user_id: int, github_username: str, error: GitHubRateLimitError, 
                              task_type: str, task_data: Dict[str, Any], 
                              original_task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle a rate limit error by scheduling automatic restart
        
        Args:
            user_id: User ID
            github_username: GitHub username
            error: The rate limit error
            task_type: Type of task ('indexing', 'sync', 'background')
            task_data: Task parameters
            original_task_id: Original task ID if applicable
            
        Returns:
            Dictionary with restart information
        """
        try:
            # Import here to avoid circular import
            from .models import RateLimitReset
            
            # Parse reset time from error message
            reset_time = RateLimitService._parse_reset_time_from_error(error)
            
            # Create rate limit reset record
            rate_limit_reset = RateLimitReset(
                user_id=user_id,
                github_username=github_username,
                rate_limit_reset_time=reset_time,
                rate_limit_remaining=0,
                pending_task_type=task_type,
                pending_task_data=task_data,
                original_task_id=original_task_id,
                status='pending'
            )
            rate_limit_reset.save()
            
            # Schedule automatic restart
            restart_scheduled = RateLimitService._schedule_restart(rate_limit_reset)
            
            logger.info(f"Rate limit hit for user {github_username}. Restart scheduled for {reset_time}")
            
            return {
                'success': True,
                'rate_limit_reset_id': str(rate_limit_reset.id),
                'reset_time': reset_time.isoformat(),
                'restart_scheduled': restart_scheduled,
                'time_until_reset': rate_limit_reset.time_until_reset,
                'message': f"Rate limit exceeded. Task will automatically restart at {reset_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            }
            
        except Exception as e:
            logger.error(f"Failed to handle rate limit error: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': "Rate limit exceeded but failed to schedule automatic restart"
            }
    
    @staticmethod
    def _parse_reset_time_from_error(error: GitHubRateLimitError) -> datetime:
        """Parse reset time from rate limit error message"""
        error_msg = str(error)
        
        # Try to extract seconds from error message
        if "Retry after" in error_msg:
            try:
                # Extract seconds from "Retry after X seconds"
                seconds_str = error_msg.split("Retry after")[1].split("seconds")[0].strip()
                wait_seconds = float(seconds_str)  # Use float to handle decimal seconds
                return datetime.utcnow() + timedelta(seconds=wait_seconds)
            except (ValueError, IndexError):
                pass
        
        # Default: wait 1 hour if we can't parse the time
        logger.warning(f"Could not parse reset time from error: {error_msg}. Using 1 hour default.")
        return datetime.utcnow() + timedelta(hours=1)
    
    @staticmethod
    def _schedule_restart(rate_limit_reset) -> bool:
        """
        Schedule automatic restart of the task
        
        Args:
            rate_limit_reset: Rate limit reset document
            
        Returns:
            True if restart was scheduled successfully
        """
        try:
            # Calculate delay until restart
            delay_seconds = rate_limit_reset.time_until_reset + 60  # Add 1 minute buffer
            
            if delay_seconds <= 0:
                # Reset time has passed, restart immediately
                RateLimitService._restart_task(rate_limit_reset)
                return True
            
            # Schedule restart using Django-Q
            task_name = RateLimitService._get_task_name(rate_limit_reset.pending_task_type)
            
            # Schedule the restart task
            schedule_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            # Create Django-Q schedule
            schedule, created = ScheduleModel.objects.get_or_create(
                name=f"rate_limit_restart_{rate_limit_reset.id}",
                defaults={
                    'func': 'analytics.services.restart_rate_limited_task',
                    'args': [str(rate_limit_reset.id)],
                    'schedule_type': ScheduleModel.ONCE,
                    'next_run': schedule_time,
                    'repeats': 1
                }
            )
            
            if not created:
                # Update existing schedule
                schedule.next_run = schedule_time
                schedule.save()
            
            # Update rate limit reset status
            rate_limit_reset.status = 'scheduled'
            rate_limit_reset.scheduled_at = datetime.utcnow()
            rate_limit_reset.save()
            
            logger.info(f"Scheduled restart for {rate_limit_reset.pending_task_type} task at {schedule_time}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule restart: {e}")
            return False
    
    @staticmethod
    def _get_task_name(task_type: str) -> str:
        """Get the task function name based on task type"""
        task_map = {
            'indexing': 'analytics.tasks.background_indexing_task',
            'sync': 'analytics.tasks.sync_application_task',
            'background': 'analytics.tasks.background_indexing_task'
        }
        return task_map.get(task_type, 'analytics.tasks.background_indexing_task')
    
    @staticmethod
    def _restart_task(rate_limit_reset) -> bool:
        """
        Restart a rate-limited task
        
        Args:
            rate_limit_reset: Rate limit reset document
            
        Returns:
            True if restart was successful
        """
        try:
            task_data = rate_limit_reset.pending_task_data
            task_name = RateLimitService._get_task_name(rate_limit_reset.pending_task_type)
            
            # Extract task parameters
            if rate_limit_reset.pending_task_type == 'indexing':
                application_id = task_data.get('application_id')
                user_id = task_data.get('user_id')
                task_id = task_data.get('task_id')
                
                # Start the background indexing task
                new_task_id = async_task(
                    task_name,
                    application_id,
                    user_id,
                    task_id,
                    group=f'rate_limit_restart_{rate_limit_reset.id}',
                    timeout=7200  # 2 hour timeout
                )
                
            elif rate_limit_reset.pending_task_type == 'sync':
                application_id = task_data.get('application_id')
                user_id = task_data.get('user_id')
                sync_type = task_data.get('sync_type', 'incremental')
                
                # Start the sync task
                new_task_id = async_task(
                    task_name,
                    application_id,
                    user_id,
                    sync_type,
                    group=f'rate_limit_restart_{rate_limit_reset.id}',
                    timeout=3600  # 1 hour timeout
                )
            
            else:
                # Generic task restart
                new_task_id = async_task(
                    task_name,
                    **task_data,
                    group=f'rate_limit_restart_{rate_limit_reset.id}',
                    timeout=3600
                )
            
            # Update rate limit reset status
            rate_limit_reset.status = 'completed'
            rate_limit_reset.completed_at = datetime.utcnow()
            rate_limit_reset.save()
            
            logger.info(f"Successfully restarted {rate_limit_reset.pending_task_type} task with ID {new_task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart task: {e}")
            rate_limit_reset.status = 'failed'
            rate_limit_reset.error_message = str(e)
            rate_limit_reset.retry_count += 1
            rate_limit_reset.save()
            return False


def restart_rate_limited_task(rate_limit_reset_id: str) -> Dict[str, Any]:
    """
    Django-Q task to restart a rate-limited task
    
    Args:
        rate_limit_reset_id: Rate limit reset document ID
        
    Returns:
        Dictionary with restart results
    """
    try:
        # Import here to avoid circular import
        from .models import RateLimitReset
        
        rate_limit_reset = RateLimitReset.objects.get(id=rate_limit_reset_id)
        
        # Check if it's time to restart
        if not rate_limit_reset.is_ready_to_restart:
            # Reschedule for later
            delay_seconds = rate_limit_reset.time_until_reset + 60
            schedule_time = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            # Update schedule
            try:
                schedule = ScheduleModel.objects.get(name=f"rate_limit_restart_{rate_limit_reset_id}")
                schedule.next_run = schedule_time
                schedule.save()
            except ScheduleModel.DoesNotExist:
                pass
            
            return {
                'success': False,
                'message': f"Not yet time to restart. Rescheduled for {schedule_time}"
            }
        
        # Restart the task
        success = RateLimitService._restart_task(rate_limit_reset)
        
        return {
            'success': success,
            'rate_limit_reset_id': rate_limit_reset_id,
            'task_type': rate_limit_reset.pending_task_type,
            'message': "Task restarted successfully" if success else "Failed to restart task"
        }
        
    except RateLimitReset.DoesNotExist:
        logger.error(f"RateLimitReset {rate_limit_reset_id} not found")
        return {
            'success': False,
            'error': 'RateLimitReset not found'
        }
    except Exception as e:
        logger.error(f"Error restarting rate-limited task: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def process_pending_rate_limit_restarts():
    """
    Django-Q task to process all pending rate limit restarts
    This can be called periodically to check for tasks that need restarting
    """
    try:
        # Import here to avoid circular import
        from .models import RateLimitReset
        
        # Find all pending rate limit resets that are ready to restart
        pending_resets = RateLimitReset.objects.filter(
            status='pending',
            rate_limit_reset_time__lte=datetime.utcnow()
        )
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for rate_limit_reset in pending_resets:
            try:
                success = RateLimitService._restart_task(rate_limit_reset)
                results['processed'] += 1
                
                if success:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    
            except Exception as e:
                results['processed'] += 1
                results['failed'] += 1
                results['errors'].append(f"Error processing {rate_limit_reset.id}: {e}")
        
        logger.info(f"Processed {results['processed']} pending rate limit restarts: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error processing pending rate limit restarts: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def cleanup_old_rate_limit_resets():
    """
    Django-Q task to clean up old rate limit resets (older than 7 days)
    """
    try:
        # Import here to avoid circular import
        from .models import RateLimitReset
        
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        # Find old rate limit resets
        old_resets = RateLimitReset.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['completed', 'failed', 'cancelled']
        )
        
        count = old_resets.count()
        old_resets.delete()
        
        logger.info(f"Cleaned up {count} old rate limit resets")
        
        return {
            'success': True,
            'cleaned_up': count
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up old rate limit resets: {e}")
        return {
            'success': False,
            'error': str(e)
        } 

from .models import Deployment
# from github.models import GitHubToken  # Deprecated - using PAT now
from applications.models import ApplicationRepository
from .github_service import GitHubService, GitHubAPIError, GitHubRateLimitError
from .github_utils import get_github_token_for_user
from typing import List

class DeploymentIndexingService:
    """Service for indexing GitHub deployments for a repository and application"""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.github_service = self._init_github_service()

    def _init_github_service(self):
        access_token = get_github_token_for_user(self.user_id)
        if not access_token:
            raise ValueError(f"No GitHub token found for user {self.user_id}")
        return GitHubService(access_token)

    def index_deployments(self, application_id: int, repo_full_name: str) -> List[str]:
        """
        Fetch and index deployments for a given repo and application.
        Returns a list of deployment IDs indexed.
        """
        url = f"{self.github_service.base_url}/repos/{repo_full_name}/deployments"
        deployments, _ = self.github_service._make_request(url)
        indexed_ids = []
        for dep in deployments:
            deployment_id = str(dep.get('id'))
            # Upsert by deployment_id
            obj, created = Deployment.objects.get_or_create(
                deployment_id=deployment_id,
                defaults={
                    'application_id': application_id,
                    'repository_full_name': repo_full_name,
                    'environment': dep.get('environment'),
                    'creator': dep.get('creator', {}).get('login'),
                    'created_at': dep.get('created_at'),
                    'updated_at': dep.get('updated_at'),
                    'payload': dep,
                }
            )
            if not created:
                # Update fields if already exists
                obj.environment = dep.get('environment')
                obj.creator = dep.get('creator', {}).get('login')
                obj.created_at = dep.get('created_at')
                obj.updated_at = dep.get('updated_at')
                obj.payload = dep
                obj.save()
            # Fetch deployment statuses
            statuses_url = f"{self.github_service.base_url}/repos/{repo_full_name}/deployments/{deployment_id}/statuses"
            statuses, _ = self.github_service._make_request(statuses_url)
            obj.statuses = statuses
            obj.save()
            indexed_ids.append(deployment_id)
        return indexed_ids 

from .models import Release
import dateutil.parser
from datetime import timezone

class ReleaseIndexingService:
    """Service for indexing GitHub releases for a repository and application"""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.github_service = self._init_github_service()

    def _init_github_service(self):
        access_token = get_github_token_for_user(self.user_id)
        if not access_token:
            raise ValueError(f"No GitHub token found for user {self.user_id}")
        return GitHubService(access_token)

    def index_releases(self, application_id: int, repo_full_name: str) -> list:
        """
        Fetch and index releases for a given repo and application.
        Returns a list of release IDs indexed.
        """
        url = f"{self.github_service.base_url}/repos/{repo_full_name}/releases"
        releases, _ = self.github_service._make_request(url)
        indexed_ids = []
        for rel in releases:
            release_id = str(rel.get('id'))
            published_at_raw = rel.get('published_at')
            published_at = None
            if published_at_raw:
                dt = dateutil.parser.parse(published_at_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published_at = dt
            obj = Release.objects.filter(release_id=release_id).first()
            if not obj:
                obj = Release(
                    release_id=release_id,
                    application_id=application_id,
                    repository_full_name=repo_full_name,
                    tag_name=rel.get('tag_name'),
                    name=rel.get('name'),
                    author=rel.get('author', {}).get('login'),
                    published_at=published_at,
                    draft=rel.get('draft', False),
                    prerelease=rel.get('prerelease', False),
                    body=rel.get('body'),
                    html_url=rel.get('html_url'),
                    assets=rel.get('assets', []),
                    payload=rel,
                )
                obj.save()
            else:
                obj.tag_name = rel.get('tag_name')
                obj.name = rel.get('name')
                obj.author = rel.get('author', {}).get('login')
                obj.published_at = published_at
                obj.draft = rel.get('draft', False)
                obj.prerelease = rel.get('prerelease', False)
                obj.body = rel.get('body')
                obj.html_url = rel.get('html_url')
                obj.assets = rel.get('assets', [])
                obj.payload = rel
                obj.save()
            indexed_ids.append(release_id)
        return indexed_ids 