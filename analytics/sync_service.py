"""
Synchronization service for fetching and storing commit data
"""
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from django.db import transaction
from mongoengine import Q

from .models import Commit, SyncLog, RepositoryStats
from .github_service import GitHubService, GitHubAPIError, GitHubRateLimitError
from applications.models import Application, ApplicationRepository
from github.models import GitHubToken

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing GitHub commit data to MongoDB"""
    
    def __init__(self, user_id: int):
        """Initialize sync service for a specific user"""
        self.user_id = user_id
        self.github_service = None
        self._init_github_service()
    
    def _init_github_service(self):
        """Initialize GitHub service with user's token"""
        try:
            github_token = GitHubToken.objects.get(user_id=self.user_id)
            self.github_service = GitHubService(github_token.access_token)
        except GitHubToken.DoesNotExist:
            raise ValueError(f"No GitHub token found for user {self.user_id}")
    
    def sync_application_repositories(self, application_id: int, sync_type: str = 'incremental') -> Dict:
        """
        Sync all repositories for an application
        
        Args:
            application_id: Application ID to sync
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        try:
            application = Application.objects.get(id=application_id, owner_id=self.user_id)
        except Application.DoesNotExist:
            raise ValueError(f"Application {application_id} not found for user {self.user_id}")
        
        repositories = ApplicationRepository.objects.filter(application=application)
        
        results = {
            'application_id': application_id,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_api_calls': 0,
            'errors': []
        }
        
        for app_repo in repositories:
            try:
                repo_result = self.sync_repository(
                    app_repo.github_repo_name,
                    application_id,
                    sync_type
                )
                results['repositories_synced'] += 1
                results['total_commits_new'] += repo_result['commits_new']
                results['total_commits_updated'] += repo_result['commits_updated']
                results['total_api_calls'] += repo_result['api_calls']
                
            except Exception as e:
                error_msg = f"Failed to sync repository {app_repo.github_repo_name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        return results
    
    def sync_repository(self, repo_full_name: str, application_id: int, 
                       sync_type: str = 'incremental') -> Dict:
        """
        Sync commits for a specific repository
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            application_id: Application ID
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        # Create sync log
        sync_log = SyncLog(
            repository_full_name=repo_full_name,
            application_id=application_id,
            sync_type=sync_type,
            status='running'
        )
        sync_log.save()
        
        try:
            # Get or create repository stats (MongoEngine way)
            repo_stats = RepositoryStats.objects(repository_full_name=repo_full_name).first()
            created = False
            if not repo_stats:
                repo_stats = RepositoryStats(
                    repository_full_name=repo_full_name,
                    application_id=application_id,
                    sync_enabled=True
                )
                repo_stats.save()
                created = True
            
            # Determine date range for sync
            since_date = None
            if sync_type == 'incremental' and repo_stats.last_commit_date:
                # Start from last synced commit date
                since_date = repo_stats.last_commit_date
            
            # Fetch commits from GitHub
            commits_data = self.github_service.get_commits(
                repo_full_name=repo_full_name,
                since=since_date,
                per_page=100
            )
            
            # Process and store commits
            results = self._process_commits(commits_data, repo_full_name, application_id)
            
            # Update repository stats
            if results['commits_processed'] > 0:
                self._update_repository_stats(repo_stats, commits_data)
            
            # Update sync log with success
            sync_log.status = 'completed'
            sync_log.completed_at = datetime.utcnow()
            sync_log.commits_processed = results['commits_processed']
            sync_log.commits_new = results['commits_new']
            sync_log.commits_updated = results['commits_updated']
            sync_log.commits_skipped = results['commits_skipped']
            sync_log.github_api_calls = results['api_calls']
            
            if commits_data:
                sync_log.last_commit_date = datetime.fromisoformat(
                    commits_data[0]['commit']['author']['date'].replace('Z', '+00:00')
                )
                sync_log.oldest_commit_date = datetime.fromisoformat(
                    commits_data[-1]['commit']['author']['date'].replace('Z', '+00:00')
                )
            
            sync_log.save()
            
            logger.info(f"Successfully synced {repo_full_name}: {results}")
            return results
            
        except (GitHubAPIError, GitHubRateLimitError) as e:
            # Handle GitHub API errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.utcnow()
            sync_log.error_message = str(e)
            sync_log.save()
            
            logger.error(f"GitHub API error syncing {repo_full_name}: {e}")
            raise
            
        except Exception as e:
            # Handle other errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.utcnow()
            sync_log.error_message = str(e)
            sync_log.error_details = {'error_type': type(e).__name__}
            sync_log.save()
            
            logger.error(f"Unexpected error syncing {repo_full_name}: {e}")
            raise
    
    def _process_commits(self, commits_data: List[Dict], repo_full_name: str, 
                        application_id: int) -> Dict:
        """
        Process and store commits to MongoDB
        
        Args:
            commits_data: List of commit data from GitHub API
            repo_full_name: Repository name
            application_id: Application ID
            
        Returns:
            Dictionary with processing results
        """
        results = {
            'commits_processed': 0,
            'commits_new': 0,
            'commits_updated': 0,
            'commits_skipped': 0,
            'api_calls': 1  # Base API call for fetching commits list
        }
        
        for commit_data in commits_data:
            try:
                sha = commit_data.get('sha')
                if not sha:
                    results['commits_skipped'] += 1
                    continue
                
                # Check if commit already exists
                existing_commit = Commit.objects(sha=sha).first()
                
                if existing_commit:
                    # Skip if already synced recently
                    if existing_commit.synced_at and \
                       (datetime.utcnow() - existing_commit.synced_at).days < 1:
                        results['commits_skipped'] += 1
                        continue
                
                # Get detailed commit data if basic data doesn't have file changes
                if 'files' not in commit_data or 'stats' not in commit_data:
                    try:
                        detailed_commit = self.github_service.get_commit_details(repo_full_name, sha)
                        commit_data.update(detailed_commit)
                        results['api_calls'] += 1
                    except GitHubAPIError as e:
                        logger.warning(f"Could not fetch details for commit {sha}: {e}")
                        # Continue with basic data
                
                # Parse commit data
                parsed_data = self.github_service.parse_commit_data(
                    commit_data, repo_full_name, application_id
                )
                
                if existing_commit:
                    # Update existing commit
                    for field, value in parsed_data.items():
                        setattr(existing_commit, field, value)
                    existing_commit.save()
                    results['commits_updated'] += 1
                else:
                    # Create new commit
                    commit = Commit(**parsed_data)
                    commit.save()
                    results['commits_new'] += 1
                
                results['commits_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing commit {commit_data.get('sha', 'unknown')}: {e}")
                results['commits_skipped'] += 1
                continue
        
        return results
    
    def _update_repository_stats(self, repo_stats: RepositoryStats, commits_data: List[Dict]):
        """Update repository statistics after sync"""
        if not commits_data:
            return
        
        # Update last sync info
        repo_stats.last_sync_at = datetime.utcnow()
        latest_commit = commits_data[0]
        repo_stats.last_commit_sha = latest_commit.get('sha')
        repo_stats.last_commit_date = datetime.fromisoformat(
            latest_commit['commit']['author']['date'].replace('Z', '+00:00')
        )
        
        # Update cached statistics
        total_commits = Commit.objects(repository_full_name=repo_stats.repository_full_name).count()
        repo_stats.total_commits = total_commits
        
        # Get unique authors count
        authors = Commit.objects(repository_full_name=repo_stats.repository_full_name).distinct('author_email')
        repo_stats.total_authors = len(authors)
        
        # Get total additions/deletions
        pipeline = [
            {'$match': {'repository_full_name': repo_stats.repository_full_name}},
            {'$group': {
                '_id': None,
                'total_additions': {'$sum': '$additions'},
                'total_deletions': {'$sum': '$deletions'}
            }}
        ]
        
        aggregation_result = list(Commit.objects.aggregate(pipeline))
        if aggregation_result:
            result = aggregation_result[0]
            repo_stats.total_additions = result.get('total_additions', 0)
            repo_stats.total_deletions = result.get('total_deletions', 0)
        
        # Get first commit date
        first_commit = Commit.objects(repository_full_name=repo_stats.repository_full_name)\
                           .order_by('authored_date').first()
        if first_commit:
            repo_stats.first_commit_date = first_commit.authored_date
        
        repo_stats.save()
    
    def retry_failed_syncs(self, max_retries: int = 3) -> Dict:
        """
        Retry failed synchronizations
        
        Args:
            max_retries: Maximum number of retries per sync
            
        Returns:
            Dictionary with retry results
        """
        # Find failed syncs within the last 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        failed_syncs = SyncLog.objects(
            status='failed',
            started_at__gte=cutoff_time,
            retry_count__lt=max_retries
        ).order_by('started_at')
        
        results = {
            'retries_attempted': 0,
            'retries_successful': 0,
            'retries_failed': 0
        }
        
        for sync_log in failed_syncs:
            try:
                # Wait before retry to handle rate limits
                time.sleep(5)
                
                # Increment retry count
                sync_log.retry_count += 1
                sync_log.save()
                
                # Retry the sync
                self.sync_repository(
                    sync_log.repository_full_name,
                    sync_log.application_id,
                    sync_log.sync_type
                )
                
                results['retries_attempted'] += 1
                results['retries_successful'] += 1
                
            except Exception as e:
                logger.error(f"Retry failed for {sync_log.repository_full_name}: {e}")
                results['retries_attempted'] += 1
                results['retries_failed'] += 1
                
                # Mark as permanently failed after max retries
                if sync_log.retry_count >= max_retries:
                    sync_log.error_message = f"Max retries exceeded: {str(e)}"
                    sync_log.save()
        
        return results 