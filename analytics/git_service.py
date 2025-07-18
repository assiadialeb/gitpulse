"""
Git service for local repository operations
"""
import os
import subprocess
import tempfile
import shutil
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Generator
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class GitServiceError(Exception):
    """Custom exception for Git service errors"""
    pass


class GitService:
    """Service for local Git operations to fetch commit data"""
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize Git service
        
        Args:
            temp_dir: Directory for temporary repository clones (optional)
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.cloned_repos = {}  # Cache for cloned repositories
        
    def clone_repository(self, repo_url: str, repo_full_name: str) -> str:
        """
        Clone a repository to a temporary directory
        
        Args:
            repo_url: Git repository URL (HTTPS or SSH)
            repo_full_name: Repository name in format "owner/repo"
            
        Returns:
            Path to cloned repository
            
        Raises:
            GitServiceError: If cloning fails
        """
        try:
            # Create unique directory for this repository
            repo_dir = os.path.join(self.temp_dir, f"gitpulse_{repo_full_name.replace('/', '_')}")
            
            # Remove existing directory if it exists
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
            
            # Clone repository
            logger.info(f"Cloning repository {repo_full_name} to {repo_dir}")
            
            # Clone without LFS to avoid large file issues
            env = os.environ.copy()
            env['GIT_LFS_SKIP_SMUDGE'] = '1'  # Skip LFS file download
            env['GIT_LFS_SKIP_PUSH'] = '1'    # Skip LFS push
            
            # First try: clone normally with LFS disabled
            result = subprocess.run(
                ['git', 'clone', '--quiet', repo_url, repo_dir],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout (increased)
                env=env
            )
            
            # If clone succeeded but checkout failed due to LFS, try to fix it
            if result.returncode != 0 and 'git-lfs' in result.stderr:
                logger.warning(f"LFS issue detected for {repo_full_name}, attempting workaround...")
                
                # Remove the failed clone
                if os.path.exists(repo_dir):
                    shutil.rmtree(repo_dir)
                
                # Clone with LFS completely disabled
                result = subprocess.run([
                    'git', '-c', 'filter.lfs.clean=', '-c', 'filter.lfs.smudge=', 
                    '-c', 'filter.lfs.process=', '-c', 'filter.lfs.required=false',
                    'clone', '--quiet', repo_url, repo_dir
                ], capture_output=True, text=True, timeout=300, env=env)
            
            if result.returncode != 0:
                raise GitServiceError(f"Failed to clone repository: {result.stderr}")

            # Fetch all branches and prune deleted ones
            fetch_result = subprocess.run(
                ['git', 'fetch', '--all', '--prune'],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=120
            )
            if fetch_result.returncode != 0:
                raise GitServiceError(f"Failed to fetch all branches: {fetch_result.stderr}")
            
            # Store in cache
            self.cloned_repos[repo_full_name] = repo_dir
            
            logger.info(f"Successfully cloned {repo_full_name}")
            return repo_dir
            
        except subprocess.TimeoutExpired:
            raise GitServiceError(f"Timeout while cloning repository {repo_full_name}")
        except Exception as e:
            raise GitServiceError(f"Error cloning repository {repo_full_name}: {str(e)}")
    
    def get_repo_path(self, repo_full_name: str) -> str:
        """
        Get the path to a cloned repository
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            
        Returns:
            Path to repository directory
        """
        if repo_full_name not in self.cloned_repos:
            raise GitServiceError(f"Repository {repo_full_name} not cloned. Call clone_repository first.")
        
        return self.cloned_repos[repo_full_name]
    
    def fetch_commits(self, repo_full_name: str, since_date: Optional[datetime] = None, 
                     max_commits: Optional[int] = None) -> List[Dict]:
        """
        Fetch commits from a local repository
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            since_date: Only fetch commits since this date (optional)
            max_commits: Maximum number of commits to fetch (optional)
            
        Returns:
            List of commit dictionaries
        """
        try:
            repo_path = self.get_repo_path(repo_full_name)
            
            # Build git log command
            cmd = ['git', 'log', '--all', '--pretty=format:%H|%an|%ae|%cn|%ce|%at|%ct|%s', '--no-merges']
            
            # Add date filter if specified
            if since_date:
                since_timestamp = int(since_date.timestamp())
                cmd.extend(['--since', str(since_timestamp)])
            
            # Add limit if specified
            if max_commits:
                cmd.extend(['-n', str(max_commits)])
            
            # Execute git log
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise GitServiceError(f"Failed to fetch commits: {result.stderr}")
            
            # Parse output
            commits = []
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                    
                parts = line.split('|')
                if len(parts) != 8:
                    continue
                
                sha, author_name, author_email, committer_name, committer_email, authored_timestamp, committed_timestamp, message = parts
                
                commit = {
                    'sha': sha,
                    'author_name': author_name,
                    'author_email': author_email,
                    'committer_name': committer_name,
                    'committer_email': committer_email,
                    'authored_date': datetime.fromtimestamp(int(authored_timestamp), timezone.utc),
                    'committed_date': datetime.fromtimestamp(int(committed_timestamp), timezone.utc),
                    'message': message
                }
                
                commits.append(commit)
            
            logger.info(f"Fetched {len(commits)} commits from {repo_full_name}")
            return commits
            
        except subprocess.TimeoutExpired:
            raise GitServiceError(f"Timeout while fetching commits from {repo_full_name}")
        except Exception as e:
            raise GitServiceError(f"Error fetching commits from {repo_full_name}: {str(e)}")
    
    def get_commit_details(self, repo_full_name: str, sha: str) -> Dict:
        """
        Get detailed information about a specific commit
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            sha: Commit SHA
            
        Returns:
            Dictionary with detailed commit information
        """
        try:
            repo_path = self.get_repo_path(repo_full_name)
            
            # Get commit stats
            stats_cmd = ['git', 'show', '--stat', '--format=%H|%an|%ae|%cn|%ce|%at|%ct|%s', sha]
            stats_result = subprocess.run(
                stats_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if stats_result.returncode != 0:
                raise GitServiceError(f"Failed to get commit details: {stats_result.stderr}")
            
            # Parse stats output
            lines = stats_result.stdout.strip().split('\n')
            if not lines:
                raise GitServiceError(f"No output for commit {sha}")
            
            # Parse commit header
            header_parts = lines[0].split('|')
            if len(header_parts) != 8:
                raise GitServiceError(f"Invalid commit header format for {sha}")
            
            sha_out, author_name, author_email, committer_name, committer_email, authored_timestamp, committed_timestamp, message = header_parts
            
            # Parse file changes
            file_changes = []
            additions = 0
            deletions = 0
            
            for line in lines[1:]:
                # Check for summary line first (e.g., "2 files changed, 2 insertions(+), 2 deletions(-)")
                if 'files changed' in line:
                    # This is the summary line, parse total stats
                    try:
                        # Extract total additions and deletions from summary
                        if 'insertions(+)' in line and 'deletions(-)' in line:
                            # Format: "2 files changed, 2 insertions(+), 2 deletions(-)"
                            parts = line.split(',')
                            for part in parts:
                                if 'insertions(+)' in part:
                                    additions = int(part.split('insertions(+)')[0].strip())
                                elif 'deletions(-)' in part:
                                    deletions = int(part.split('deletions(-)')[0].strip())
                        elif 'insertions(+)' in line:
                            # Only additions
                            additions = int(line.split('insertions(+)')[0].split(',')[-1].strip())
                            deletions = 0
                        elif 'deletions(-)' in line:
                            # Only deletions
                            deletions = int(line.split('deletions(-)')[0].split(',')[-1].strip())
                            additions = 0
                    except (ValueError, IndexError):
                        # Skip if we can't parse the summary
                        pass
                    continue
                
                # Check for individual file changes
                if line.startswith(' ') and '|' in line:
                    # Parse file line like "filename | 2 +-"
                    parts = line.strip().split('|')
                    if len(parts) >= 2:
                        filename = parts[0].strip()
                        change_info = parts[1].strip()
                        
                        # Parse change info like "2 +-" or "171 +++++++++++++--------------"
                        try:
                            file_additions = 0
                            file_deletions = 0
                            
                            # Count + and - characters
                            if '+' in change_info and '-' in change_info:
                                # Both additions and deletions
                                plus_count = change_info.count('+')
                                minus_count = change_info.count('-')
                                
                                # Estimate additions/deletions based on the visual representation
                                # Each + or - represents roughly 1 line
                                file_additions = plus_count
                                file_deletions = minus_count
                                
                            elif '+' in change_info:
                                # Only additions
                                plus_count = change_info.count('+')
                                file_additions = plus_count
                                file_deletions = 0
                                
                            elif '-' in change_info:
                                # Only deletions
                                minus_count = change_info.count('-')
                                file_additions = 0
                                file_deletions = minus_count
                            
                            if file_additions > 0 or file_deletions > 0:
                                file_changes.append({
                                    'filename': filename,
                                    'additions': file_additions,
                                    'deletions': file_deletions,
                                    'changes': file_additions + file_deletions,
                                    'status': 'modified' if file_additions > 0 and file_deletions > 0 else ('added' if file_additions > 0 else 'removed')
                                })
                            
                        except (ValueError, IndexError):
                            # Skip if we can't parse the numbers
                            continue
            
            commit_details = {
                'sha': sha,
                'author_name': author_name,
                'author_email': author_email,
                'committer_name': committer_name,
                'committer_email': committer_email,
                'authored_date': datetime.fromtimestamp(int(authored_timestamp), timezone.utc),
                'committed_date': datetime.fromtimestamp(int(committed_timestamp), timezone.utc),
                'message': message,
                'additions': additions,
                'deletions': deletions,
                'total_changes': additions + deletions,
                'files_changed': file_changes
            }
            
            return commit_details
            
        except subprocess.TimeoutExpired:
            raise GitServiceError(f"Timeout while getting commit details for {sha}")
        except Exception as e:
            raise GitServiceError(f"Error getting commit details for {sha}: {str(e)}")
    
    def get_repository_info(self, repo_full_name: str) -> Dict:
        """
        Get basic repository information
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            
        Returns:
            Dictionary with repository information
        """
        try:
            repo_path = self.get_repo_path(repo_full_name)
            
            # Get remote URL
            remote_cmd = ['git', 'config', '--get', 'remote.origin.url']
            remote_result = subprocess.run(
                remote_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            remote_url = remote_result.stdout.strip() if remote_result.returncode == 0 else None
            
            # Get first and last commit dates
            first_commit_cmd = ['git', 'log', '--reverse', '--format=%at', '--max-count=1']
            first_result = subprocess.run(
                first_commit_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            last_commit_cmd = ['git', 'log', '--format=%at', '--max-count=1']
            last_result = subprocess.run(
                last_commit_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            first_date = None
            last_date = None
            
            if first_result.returncode == 0 and first_result.stdout.strip():
                first_timestamp = int(first_result.stdout.strip())
                first_date = datetime.fromtimestamp(first_timestamp, timezone.utc)
            
            if last_result.returncode == 0 and last_result.stdout.strip():
                last_timestamp = int(last_result.stdout.strip())
                last_date = datetime.fromtimestamp(last_timestamp, timezone.utc)
            
            # Get total commit count
            count_cmd = ['git', 'rev-list', '--count', 'HEAD']
            count_result = subprocess.run(
                count_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            total_commits = 0
            if count_result.returncode == 0 and count_result.stdout.strip():
                total_commits = int(count_result.stdout.strip())
            
            return {
                'repository_full_name': repo_full_name,
                'remote_url': remote_url,
                'first_commit_date': first_date,
                'last_commit_date': last_date,
                'total_commits': total_commits
            }
            
        except Exception as e:
            raise GitServiceError(f"Error getting repository info for {repo_full_name}: {str(e)}")
    
    def cleanup_repository(self, repo_full_name: str):
        """
        Clean up a cloned repository
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
        """
        if repo_full_name in self.cloned_repos:
            repo_path = self.cloned_repos[repo_full_name]
            try:
                shutil.rmtree(repo_path)
                logger.info(f"Cleaned up repository {repo_full_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup repository {repo_full_name}: {e}")
            finally:
                del self.cloned_repos[repo_full_name]
    
    def cleanup_all_repositories(self):
        """Clean up all cloned repositories"""
        for repo_full_name in list(self.cloned_repos.keys()):
            self.cleanup_repository(repo_full_name) 