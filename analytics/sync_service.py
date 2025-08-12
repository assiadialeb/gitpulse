"""
Synchronization service for fetching and storing commit data
"""
import time
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List, Dict, Optional, Tuple
from django.db import transaction
from mongoengine import Q
from mongoengine.errors import NotUniqueError

from .models import Commit, SyncLog, RepositoryStats
from .sanitization import assert_safe_repository_full_name
from .github_service import GitHubService, GitHubAPIError, GitHubRateLimitError
# Note: Legacy 'Application' model has been removed.
# Any application-centric sync paths have been adapted to use 'Project' if needed,
# and repository-based indexing should call sync_repository directly.
from .github_token_service import GitHubTokenService
from .services import RateLimitService

# from github.models import GitHubToken  # Deprecated - using OAuth App now

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
        # Use the new token service for repository access
        access_token = GitHubTokenService.get_token_for_operation('private_repos', self.user_id)
        if not access_token:
            raise ValueError(f"No GitHub token found for user {self.user_id}")
        self.github_service = GitHubService(access_token)
    
    def sync_application_repositories(self, application_id: int, sync_type: str = 'incremental') -> Dict:
        """
        Sync all repositories for a project (legacy API name kept for backward compatibility)
        
        Args:
            application_id: Application ID to sync
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        try:
            from projects.models import Project
            project = Project.objects.get(id=application_id)
        except Exception:
            raise ValueError(f"Project {application_id} not found")
        
        repositories = project.repositories.all()
        
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
                    app_repo.full_name,
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

    def sync_application_repositories_with_progress(self, application_id: int, sync_type: str = 'incremental') -> Dict:
        """
        Sync all repositories for a project with progress tracking (legacy API name kept)
        
        Args:
            application_id: Application ID to sync
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        try:
            from projects.models import Project
            project = Project.objects.get(id=application_id)
        except Exception:
            raise ValueError(f"Project {application_id} not found")
        
        repositories = project.repositories.all()
        total_repos = repositories.count()
        
        results = {
            'application_id': application_id,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_api_calls': 0,
            'errors': [],
            'total_repositories': total_repos
        }
        
        for i, app_repo in enumerate(repositories, 1):
            try:
                logger.info(f"Syncing repository {i}/{total_repos}: {app_repo.full_name}")
                
                repo_result = self.sync_repository(
                    app_repo.full_name,
                    application_id,
                    sync_type
                )
                results['repositories_synced'] += 1
                results['total_commits_new'] += repo_result['commits_new']
                results['total_commits_updated'] += repo_result['commits_updated']
                results['total_api_calls'] += repo_result['api_calls']
                
                logger.info(f"Completed {i}/{total_repos} repositories")
                
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
            assert_safe_repository_full_name(repo_full_name)
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
            sync_log.completed_at = datetime.now(dt_timezone.utc)
            sync_log.commits_processed = results['commits_processed']
            sync_log.commits_new = results['commits_new']
            sync_log.commits_updated = results['commits_updated']
            sync_log.commits_skipped = results['commits_skipped']
            sync_log.github_api_calls = results['api_calls']
            
            if commits_data:
                sync_log.last_commit_date = commits_data[0]['authored_date']
                sync_log.oldest_commit_date = commits_data[-1]['authored_date']
            
            sync_log.save()
            
            logger.info(f"Successfully synced {repo_full_name}: {results}")
            return results
            
        except GitHubRateLimitError as e:
            # Handle rate limit errors with automatic restart
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.now(dt_timezone.utc)
            sync_log.error_message = str(e)
            sync_log.save()
            
            logger.error(f"Rate limit exceeded syncing {repo_full_name}: {e}")
            
            # Get user's GitHub username for rate limit service
            try:
                # Try to get username from GitHub API using OAuth App
                access_token = GitHubTokenService.get_token_for_operation('basic')
                if access_token:
                    github_service = GitHubService(access_token)
                    user_info, _ = github_service._make_request("https://api.github.com/user")
                    github_username = user_info.get('login', f"user_{self.user_id}")
                else:
                    github_username = f"user_{self.user_id}"
            except Exception:
                github_username = f"user_{self.user_id}"
            
            # Handle rate limit with automatic restart
            task_data = {
                'application_id': application_id,
                'user_id': self.user_id,
                'sync_type': sync_type
            }
            
            restart_info = RateLimitService.handle_rate_limit_error(
                user_id=self.user_id,
                github_username=github_username,
                error=e,
                task_type='sync',
                task_data=task_data
            )
            
            # Return restart information instead of raising
            return {
                'commits_new': 0,
                'commits_updated': 0,
                'commits_processed': 0,
                'commits_skipped': 0,
                'api_calls': 0,
                'rate_limit_hit': True,
                'restart_info': restart_info
            }
            
        except GitHubAPIError as e:
            # Handle other GitHub API errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.now(dt_timezone.utc)
            sync_log.error_message = str(e)
            sync_log.save()
            
            logger.error(f"GitHub API error syncing {repo_full_name}: {e}")
            raise
            
        except Exception as e:
            # Handle other errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.now(dt_timezone.utc)
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
                
                # Check if commit already exists for this repository
                assert_safe_repository_full_name(repo_full_name)
                existing_commit = Commit.objects(sha=sha, repository_full_name=repo_full_name).first()
                
                if existing_commit:
                    # Remove skip logic - always process commits for full re-indexing
                    # # Skip if already synced recently (within 1 day)
                    # if existing_commit.synced_at:
                    #     # Ensure synced_at is timezone-aware for comparison
                    #     synced_at = existing_commit.synced_at
                    #     if synced_at.tzinfo is None:
                    #         synced_at = synced_at.replace(tzinfo=dt_timezone.utc)
                    #     
                    #     if (datetime.now(dt_timezone.utc) - synced_at).days < 1:
                    #         results['commits_skipped'] += 1
                    #         continue
                    pass
                
                # Get detailed commit data if basic data doesn't have file changes
                if 'files' not in commit_data or 'stats' not in commit_data:
                    try:
                        detailed_commit = self.github_service.get_commit_details(repo_full_name, sha)
                        commit_data.update(detailed_commit)
                        results['api_calls'] += 1
                    except GitHubRateLimitError as e:
                        logger.warning(f"Rate limit hit while fetching details for commit {sha}: {e}")
                        # Stop processing commits and raise rate limit error
                        raise
                    except GitHubAPIError as e:
                        logger.warning(f"Could not fetch details for commit {sha}: {e}")
                        # Continue with basic data
                        pass
                
                # Parse commit data
                parsed_data = self.github_service.parse_commit_data(
                    commit_data, repo_full_name, application_id
                )
                # Ensure files_changed contains EmbeddedDocument instances, not raw dicts
                try:
                    from .models import FileChange
                    raw_file_changes = parsed_data.get('files_changed', []) or []
                    file_changes_embedded = []
                    for fc in raw_file_changes:
                        if isinstance(fc, FileChange):
                            file_changes_embedded.append(fc)
                        elif isinstance(fc, dict):
                            file_changes_embedded.append(
                                FileChange(
                                    filename=fc.get('filename', ''),
                                    additions=int(fc.get('additions', 0) or 0),
                                    deletions=int(fc.get('deletions', 0) or 0),
                                    changes=int(fc.get('changes', 0) or 0),
                                    status=fc.get('status', 'modified'),
                                    patch=fc.get('patch')
                                )
                            )
                    parsed_data['files_changed'] = file_changes_embedded
                except Exception:
                    # On any parsing issue, fallback to empty list to avoid ValidationError
                    parsed_data['files_changed'] = []
                
                if existing_commit:
                    # Update existing commit
                    for field, value in parsed_data.items():
                        setattr(existing_commit, field, value)
                    existing_commit.save()
                    results['commits_updated'] += 1
                else:
                    # Create new commit
                    try:
                        commit = Commit(**parsed_data)
                        commit.save()
                        results['commits_new'] += 1
                    except NotUniqueError:
                        logger.warning(f"Commit {sha} déjà présent, ignoré.")
                        results['commits_skipped'] += 1
                        continue
                
                results['commits_processed'] += 1
                
            except GitHubRateLimitError as e:
                # Re-raise rate limit errors to stop processing
                logger.error(f"Rate limit exceeded processing commit {commit_data.get('sha', 'unknown')}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error processing commit {commit_data.get('sha', 'unknown')}: {e}")
                results['commits_skipped'] += 1
                continue
        
        return results
    
    def _update_repository_stats(self, repo_stats: RepositoryStats, commits_data: List[Dict]):
        """Update repository statistics with latest commit data"""
        if not commits_data:
            return
        
        # Update last commit date
        latest_commit = commits_data[0]
        repo_stats.last_commit_date = latest_commit['authored_date']
        
        # Update oldest commit date if this is the first sync or if we found older commits
        oldest_commit = commits_data[-1]
        if not repo_stats.oldest_commit_date or oldest_commit['authored_date'] < repo_stats.oldest_commit_date:
            repo_stats.oldest_commit_date = oldest_commit['authored_date']
        
        # Update commit count
        assert_safe_repository_full_name(repo_stats.repository_full_name)
        repo_stats.total_commits = Commit.objects(repository_full_name=repo_stats.repository_full_name).count()
        
        # Update last sync time
        repo_stats.last_sync_at = datetime.now(dt_timezone.utc)
        
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
        cutoff_time = datetime.now(dt_timezone.utc) - timedelta(hours=24)
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