"""
Git-based synchronization service for fetching and storing commit data
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List, Dict, Optional, Tuple
from django.db import transaction
from mongoengine import Q
from django.core.exceptions import ObjectDoesNotExist
from pymongo import MongoClient
from mongoengine.errors import NotUniqueError

from .models import Commit, SyncLog, RepositoryStats, FileChange
from .git_service import GitService, GitServiceError
from .sanitization import assert_safe_repository_full_name

from .commit_classifier import classify_commit_with_files
from analytics.models import DeveloperAlias

logger = logging.getLogger(__name__)


class GitSyncService:
    """Service for synchronizing Git commit data to MongoDB using local Git operations"""
    
    def __init__(self, user_id: int):
        """Initialize sync service for a specific user"""
        self.user_id = user_id
        self.git_service = GitService()
        # Get GitHub token for authentication
        from .github_token_service import GitHubTokenService
        self.github_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
        if not self.github_token:
            self.github_token = GitHubTokenService._get_user_token(user_id)
        if not self.github_token:
            self.github_token = GitHubTokenService._get_oauth_app_token()
    
    def sync_application_repositories(self, application_id: int, sync_type: str = 'incremental') -> Dict:
        """
        Sync all repositories for an application using Git local operations
        
        Args:
            application_id: Application ID to sync
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        try:
            application = Application.objects.get(id=application_id, owner_id=self.user_id)
        except ObjectDoesNotExist:
            raise ValueError(f"Application {application_id} not found for user {self.user_id}")
        
        repositories = application.repositories.all()
        
        results = {
            'application_id': application_id,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_commits_processed': 0,
            'errors': []
        }
        
        try:
            for app_repo in repositories:
                try:
                    repo_result = self.sync_repository(
                        app_repo.github_repo_name,
                        app_repo.github_repo_url,
                        application_id,
                        sync_type
                    )
                    results['repositories_synced'] += 1
                    results['total_commits_new'] += repo_result['commits_new']
                    results['total_commits_updated'] += repo_result['commits_updated']
                    results['total_commits_processed'] += repo_result['commits_processed']
                    
                except Exception as e:
                    error_msg = f"Failed to sync repository {app_repo.github_repo_name}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        finally:
            # Clean up all cloned repositories
            self.git_service.cleanup_all_repositories()

        return results

    def sync_application_repositories_with_progress(self, application_id: int, sync_type: str = 'incremental') -> Dict:
        """
        Sync all repositories for an application with progress tracking
        
        Args:
            application_id: Application ID to sync
            sync_type: 'full' or 'incremental'
            
        Returns:
            Dictionary with sync results
        """
        try:
            application = Application.objects.get(id=application_id, owner_id=self.user_id)
        except ObjectDoesNotExist:
            raise ValueError(f"Application {application_id} not found for user {self.user_id}")
        
        repositories = application.repositories.all()
        total_repos = repositories.count()
        
        results = {
            'application_id': application_id,
            'repositories_synced': 0,
            'total_commits_new': 0,
            'total_commits_updated': 0,
            'total_commits_processed': 0,
            'errors': [],
            'total_repositories': total_repos
        }
        
        try:
            for i, app_repo in enumerate(repositories, 1):
                try:
                    logger.info(f"Syncing repository {i}/{total_repos}: {app_repo.github_repo_name}")
                    
                    repo_result = self.sync_repository(
                        app_repo.github_repo_name,
                        app_repo.github_repo_url,
                        application_id,
                        sync_type
                    )
                    results['repositories_synced'] += 1
                    results['total_commits_new'] += repo_result['commits_new']
                    results['total_commits_updated'] += repo_result['commits_updated']
                    results['total_commits_processed'] += repo_result['commits_processed']
                    
                    logger.info(f"Completed {i}/{total_repos} repositories")
                    
                except Exception as e:
                    error_msg = f"Failed to sync repository {app_repo.github_repo_name}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        finally:
            # Clean up all cloned repositories
            self.git_service.cleanup_all_repositories()

        return results
    
    def sync_repository(self, repo_full_name: str, repo_url: str, application_id: int = None, 
                       sync_type: str = 'incremental') -> Dict:
        """
        Sync commits for a specific repository using Git local operations
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            repo_url: Git repository URL
            application_id: Application ID (optional for repository-based indexing)
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
            # Clone repository
            print(f"DEBUG: About to clone repository {repo_full_name} from {repo_url}")
            logger.info(f"Cloning repository {repo_full_name} from {repo_url}")
            try:
                repo_path = self.git_service.clone_repository(repo_url, repo_full_name, self.github_token)
                print(f"DEBUG: Successfully cloned {repo_full_name} to {repo_path}")
                logger.info(f"Successfully cloned {repo_full_name} to {repo_path}")
            except Exception as clone_error:
                print(f"DEBUG: Failed to clone {repo_full_name}: {clone_error}")
                logger.error(f"Failed to clone {repo_full_name}: {clone_error}")
                raise
            
            # Validate repository name before Mongo queries and get or create repository stats
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
                since_date = repo_stats.last_commit_date.to_datetime() if hasattr(repo_stats.last_commit_date, 'to_datetime') else repo_stats.last_commit_date
            # For 'full' sync, since_date remains None to get ALL commits from the beginning of time
            
            # Fetch commits from Git
            commits_data = self.git_service.fetch_commits(
                repo_full_name=repo_full_name,
                since_date=since_date
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
            sync_log.github_api_calls = 0  # No API calls with Git local
            
            if commits_data:
                sync_log.last_commit_date = commits_data[0]['authored_date']
                sync_log.oldest_commit_date = commits_data[-1]['authored_date']
            
            sync_log.save()
            
            logger.info(f"Successfully synced {repo_full_name}: {results}")
            return results
            
        except GitServiceError as e:
            # Handle Git service errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.now(dt_timezone.utc)
            sync_log.error_message = str(e)
            sync_log.save()
            
            logger.error(f"Git service error syncing {repo_full_name}: {e}")
            raise
            
        except Exception as e:
            # Handle other errors
            sync_log.status = 'failed'
            sync_log.completed_at = datetime.now(dt_timezone.utc)
            sync_log.error_message = str(e)
            sync_log.save()
            
            logger.error(f"Error syncing {repo_full_name}: {e}")
            raise
        finally:
            # Always clean up the cloned repository after syncing (success or failure)
            try:
                self.git_service.cleanup_repository(repo_full_name)
                logger.info(f"Cleaned up cloned repository for {repo_full_name}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup cloned repository for {repo_full_name}: {cleanup_error}")
    
    def _process_commits(self, commits_data: List[Dict], repo_full_name: str, 
                        application_id: int = None) -> Dict:
        """
        Process and store commits in MongoDB
        
        Args:
            commits_data: List of commit dictionaries from Git
            repo_full_name: Repository name
            application_id: Application ID (optional for repository-based indexing)
            
        Returns:
            Dictionary with processing results
        """
        results = {
            'commits_new': 0,
            'commits_updated': 0,
            'commits_processed': 0,
            'commits_skipped': 0
        }
        
        logger.info(f"Processing {len(commits_data)} commits for {repo_full_name}")
        
        for commit_data in commits_data:
            try:
                sha = commit_data.get('sha')
                if not sha:
                    logger.warning(f"Commit missing SHA, skipping")
                    results['commits_skipped'] += 1
                    continue
                
                logger.debug(f"Processing commit {sha[:8]} by {commit_data.get('author_name', 'unknown')}")
                
                # Check if commit already exists for this repository
                assert_safe_repository_full_name(repo_full_name)
                existing_commit = Commit.objects(sha=sha, repository_full_name=repo_full_name).first()
                
                if existing_commit:
                    logger.debug(f"Commit {sha[:8]} already exists, will update")
                    # Remove skip logic - always process commits for full re-indexing
                    # if existing_commit.synced_at:
                    #     # Ensure synced_at is timezone-aware for comparison
                    #     synced_at = existing_commit.synced_at
                    #     if synced_at.tzinfo is None:
                    #         synced_at = synced_at.replace(tzinfo=dt_timezone.utc)
                    #     
                    #     if (datetime.now(dt_timezone.utc) - synced_at).days < 1:
                    #         logger.debug(f"Commit {sha[:8]} synced recently, skipping")
                    #         results['commits_skipped'] += 1
                    #         continue
                
                # Get detailed commit data with file changes
                try:
                    detailed_commit = self.git_service.get_commit_details(repo_full_name, sha)
                    commit_data.update(detailed_commit)
                    logger.debug(f"Got details for commit {sha[:8]}: {detailed_commit.get('additions', 0)} additions, {detailed_commit.get('deletions', 0)} deletions")
                except GitServiceError as e:
                    logger.warning(f"Could not fetch details for commit {sha[:8]}: {e}. Using basic data.")
                    # Continue with basic data
                
                # Parse commit data
                parsed_data = self._parse_commit_data(commit_data, repo_full_name, application_id)
                
                # Add commit classification with files (docs/chore auto)
                parsed_data['commit_type'] = classify_commit_with_files(
                    commit_data.get('message', ''),
                    [f['filename'] for f in commit_data.get('files_changed', [])]
                )
                
                # Store or update commit
                if existing_commit:
                    # Update existing commit
                    logger.debug(f"Updating existing commit {sha[:8]}")
                    for field, value in parsed_data.items():
                        if field != 'sha':  # Don't update SHA
                            setattr(existing_commit, field, value)
                    existing_commit.save()
                    results['commits_updated'] += 1
                else:
                    # Create new commit
                    try:
                        logger.debug(f"Creating new commit {sha[:8]} by {parsed_data.get('author_name', 'unknown')}")
                        commit = Commit(**parsed_data)
                        commit.save()
                        results['commits_new'] += 1
                        logger.info(f"Successfully created commit {sha[:8]} by {parsed_data.get('author_name', 'unknown')}")
                    except NotUniqueError:
                        logger.warning(f"Commit {sha[:8]} already present, skipping")
                        results['commits_skipped'] += 1
                        continue
                
                results['commits_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing commit {commit_data.get('sha', 'unknown')}: {e}")
                results['commits_skipped'] += 1
                continue
        
        logger.info(f"Processed {results['commits_processed']} commits for {repo_full_name}: {results['commits_new']} new, {results['commits_updated']} updated, {results['commits_skipped']} skipped")
        return results
    
    def _parse_commit_data(self, commit_data: Dict, repo_full_name: str, application_id: int = None) -> Dict:
        """
        Parse commit data into MongoDB document format
        
        Args:
            commit_data: Raw commit data from Git
            repo_full_name: Repository name
            application_id: Application ID (optional for repository-based indexing)
            
        Returns:
            Dictionary ready for MongoDB storage
        """
        # Parse file changes
        file_changes = []
        if 'files_changed' in commit_data:
            for file_data in commit_data['files_changed']:
                file_change = FileChange(
                    filename=file_data['filename'],
                    additions=file_data['additions'],
                    deletions=file_data['deletions'],
                    changes=file_data['changes'],
                    status=file_data['status']
                )
                file_changes.append(file_change)
        
        parsed_data = {
            'sha': commit_data.get('sha'),
            'repository_full_name': repo_full_name,
            'application_id': application_id,
            'message': commit_data.get('message', ''),
            'author_name': commit_data.get('author_name', ''),
            'author_email': commit_data.get('author_email', ''),
            'committer_name': commit_data.get('committer_name', ''),
            'committer_email': commit_data.get('committer_email', ''),
            'authored_date': commit_data.get('authored_date'),
            'committed_date': commit_data.get('committed_date'),
            'additions': commit_data.get('additions', 0),
            'deletions': commit_data.get('deletions', 0),
            'total_changes': commit_data.get('total_changes', 0),
            'files_changed': file_changes,
            'parent_shas': [],  # Git local doesn't provide parent SHAs easily
            'tree_sha': '',  # Git local doesn't provide tree SHA easily
            'url': f"https://github.com/{repo_full_name}/commit/{commit_data.get('sha')}",
            'synced_at': datetime.now(dt_timezone.utc)
        }
        
        return parsed_data
    
    def _update_repository_stats(self, repo_stats: RepositoryStats, commits_data: List[Dict]):
        """
        Update repository statistics
        
        Args:
            repo_stats: RepositoryStats document
            commits_data: List of processed commits
        """
        if not commits_data:
            return
        
        # Update last commit info
        latest_commit = commits_data[0]  # Commits are ordered newest first
        repo_stats.last_commit_sha = latest_commit['sha']
        repo_stats.last_commit_date = latest_commit['authored_date']
        repo_stats.last_sync_at = datetime.now(dt_timezone.utc)
        
        # Update first commit info if not set
        if not repo_stats.first_commit_date:
            oldest_commit = commits_data[-1]  # Last in list is oldest
            repo_stats.first_commit_date = oldest_commit['authored_date']
        
        # Update totals
        assert_safe_repository_full_name(repo_stats.repository_full_name)
        repo_stats.total_commits = Commit.objects(repository_full_name=repo_stats.repository_full_name).count()
        
        # Count unique authors
        assert_safe_repository_full_name(repo_stats.repository_full_name)
        unique_authors = Commit.objects(repository_full_name=repo_stats.repository_full_name).distinct('author_email')
        repo_stats.total_authors = len(unique_authors)
        
        # Calculate total additions/deletions
        total_additions = sum(int(commit.get('additions', 0)) for commit in commits_data)
        total_deletions = sum(int(commit.get('deletions', 0)) for commit in commits_data)
        repo_stats.total_additions = int(repo_stats.total_additions or 0) + total_additions
        repo_stats.total_deletions = int(repo_stats.total_deletions or 0) + total_deletions
        
        repo_stats.save()
    
    def cleanup(self):
        """Clean up all cloned repositories"""
        self.git_service.cleanup_all_repositories() 

def create_missing_aliases_for_application(application_id: int):
    """Create missing aliases for all unique authors in an application"""
    logger.info(f"Creating missing aliases for application {application_id}...")
    
    # Get all unique authors from commits
    client = MongoClient('localhost', 27017)
    db = client['gitpulse']
    
    # Extract unique authors from commits
    unique_authors = set()
    for commit in db.commits.find({'application_id': application_id}):
        author_key = f"{commit.get('author_name', '')}|{commit.get('author_email', '')}"
        unique_authors.add(author_key)
    
    logger.info(f"Found {len(unique_authors)} unique authors")
    
    # Create missing aliases
    created_count = 0
    for author_key in unique_authors:
        name, email = author_key.split('|', 1)
        
        # Check if alias already exists
        existing_alias = DeveloperAlias.objects(
            name=name,
            email=email
        ).first()
        
        if not existing_alias:
            # Create new alias
            alias = DeveloperAlias(
                name=name,
                email=email,
                            first_seen=datetime.now(dt_timezone.utc),  # Will be updated with actual dates later
            last_seen=datetime.now(dt_timezone.utc),
                commit_count=1
            )
            alias.save()
            created_count += 1
            logger.info(f"Created alias: {name} ({email})")
    
    logger.info(f"Created {created_count} new aliases")
    return created_count 