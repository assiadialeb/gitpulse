"""
Git service for local repository operations
"""
import os
import re
import subprocess
import tempfile
import shutil
import logging
import threading
import time
from datetime import datetime, timezone as dt_timezone
from typing import List, Dict, Optional, Tuple, Generator
from pathlib import Path
import json
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


class GitServiceError(Exception):
    """Custom exception for Git service errors"""
    pass


class GitService:
    """Service for local Git operations to fetch commit data"""
    
    # Class-level locks for repository operations
    _clone_locks = {}  # Only for cloning operations
    _locks_lock = threading.Lock()
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize Git service
        
        Args:
            temp_dir: Directory for temporary repository clones (optional)
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.cloned_repos = {}  # Cache for cloned repositories
        
    def _get_clone_lock(self, repo_full_name: str) -> threading.Lock:
        """Get or create a lock specifically for cloning operations on a repository"""
        with self._locks_lock:
            clone_key = f"clone_{repo_full_name}"
            if clone_key not in self._clone_locks:
                self._clone_locks[clone_key] = threading.Lock()
            return self._clone_locks[clone_key]
    
    def clone_repository(self, repo_url: str, repo_full_name: str, github_token: str = None, default_branch: str = None) -> str:
        """
        Clone a repository to a temporary directory with concurrency protection
        
        Args:
            repo_url: Git repository URL (HTTPS or SSH)
            repo_full_name: Repository name in format "owner/repo"
            github_token: GitHub token for authentication (optional)
            default_branch: Default branch to clone (optional, will use repository default if not specified)
            
        Returns:
            Path to cloned repository
            
        Raises:
            GitServiceError: If cloning fails
        """
        # Get repository-specific lock to prevent concurrent clones
        clone_lock = self._get_clone_lock(repo_full_name)
        
        with clone_lock:
            logger.info(f"Acquired lock for cloning {repo_full_name}")
            
            try:
                # Validate inputs and sanitize directory name
                self._validate_repo_inputs(repo_url, repo_full_name)
                safe_dir_name = self._sanitize_repo_dir_name(repo_full_name)
                # Create unique directory for this repository
                repo_dir = os.path.join(self.temp_dir, f"gitpulse_{safe_dir_name}")
                
                # Check if already exists and is valid
                if os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, '.git')):
                    logger.info(f"Repository {repo_full_name} already cloned at {repo_dir}")
                    return repo_dir
                
                # Remove existing directory if it exists but is invalid
                if os.path.exists(repo_dir):
                    logger.info(f"Removing invalid clone directory for {repo_full_name}")
                    shutil.rmtree(repo_dir)
            
                # Clone repository
                logger.info(f"Cloning repository {repo_full_name} to {repo_dir}")
                
                # Clone without LFS to avoid large file issues
                env = os.environ.copy()
                env['GIT_LFS_SKIP_SMUDGE'] = '1'  # Skip LFS file download
                env['GIT_LFS_SKIP_PUSH'] = '1'    # Skip LFS push
                env['GIT_TERMINAL_PROMPT'] = '0'  # Disable interactive prompts
                
                # Prepare clone URL with authentication if token provided
                clone_url = self._build_authenticated_url(repo_url, github_token)
                if github_token and clone_url != repo_url:
                    logger.info(f"Using authenticated clone URL for {repo_full_name}")
                
                # Validate arguments for git commands
                self._assert_safe_git_args(clone_url, repo_dir)

                # First try: clone normally with LFS disabled
                result = subprocess.run(
                    ['git', 'clone', '--quiet', clone_url, repo_dir],
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes timeout (increased)
                    env=env
                )
                
                # Check if first clone succeeded
                if result.returncode == 0:
                    strategy_used = 1  # Normal clone succeeded
                else:
                    # First clone failed, try alternative strategies
                    logger.warning(f"Initial clone failed for {repo_full_name}: {result.stderr}")
                    
                    # Remove the failed clone
                    if os.path.exists(repo_dir):
                        shutil.rmtree(repo_dir)
                    
                    # Clone with multiple strategies for robustness
                    clone_strategies = []
                    
                    if default_branch:
                        # Strategy 1: Clone specific default branch (most reliable for KLOC)
                        clone_strategies.append(
                            self._build_git_command('clone', clone_url, repo_dir, 
                                                  extra=['--branch', default_branch, '--depth=1', '--quiet'], 
                                                  disable_lfs=True)
                        )
                        # Strategy 2: Clone specific default branch without depth limit
                        clone_strategies.append(
                            self._build_git_command('clone', clone_url, repo_dir, 
                                                  extra=['--branch', default_branch, '--quiet'], 
                                                  disable_lfs=True)
                        )
                    
                    # Fallback strategies (original ones)
                    clone_strategies.extend([
                        # Strategy 3: Shallow clone without LFS (fastest, most reliable)
                        self._build_git_command('clone', clone_url, repo_dir, extra=['--depth=1', '--no-single-branch', '--quiet'], disable_lfs=True),
                        # Strategy 4: Full clone without LFS (if shallow fails)
                        self._build_git_command('clone', clone_url, repo_dir, extra=['--quiet'], disable_lfs=True),
                        # Strategy 5: Bare clone (minimal, no working directory)
                        self._build_git_command('clone', clone_url, repo_dir, extra=['--bare', '--quiet'], disable_lfs=True),
                    ])
                    
                    result = None
                    strategy_used = None
                    
                    for i, strategy in enumerate(clone_strategies, 1):
                        logger.info(f"Trying clone strategy {i} for {repo_full_name}")
                        
                        # Clean up any partial clone
                        if os.path.exists(repo_dir):
                            shutil.rmtree(repo_dir)
                        
                        result = subprocess.run(
                            strategy, 
                            capture_output=True, 
                            text=True, 
                            timeout=600,  # Increased timeout
                            env=env
                        )
                        
                        if result.returncode == 0:
                            strategy_used = i
                            logger.info(f"Clone strategy {i} succeeded for {repo_full_name}")
                            break
                        else:
                            logger.warning(f"Clone strategy {i} failed for {repo_full_name}: {result.stderr}")
                    
                    if not strategy_used:
                        # All strategies failed
                        error_msg = result.stderr.lower()
                        
                        # Detect common error types for better error messages
                        if 'repository not found' in error_msg or 'not found' in error_msg:
                            raise GitServiceError(f"Repository not found or private: {repo_full_name}")
                        elif 'permission denied' in error_msg or 'authentication failed' in error_msg:
                            raise GitServiceError(f"Authentication failed for repository: {repo_full_name}")
                        elif 'tmp_pack' in error_msg or 'pack' in error_msg:
                            # Try one more time with minimal clone for pack errors
                            logger.warning(f"Pack error detected for {repo_full_name}, trying minimal clone...")
                            
                            # Clean up failed attempt
                            if os.path.exists(repo_dir):
                                shutil.rmtree(repo_dir)
                            
                            # Wait to avoid resource conflicts
                            time.sleep(3)
                            
                            # Try minimal clone (depth=1, single branch)
                            minimal_cmd = self._build_git_command('clone', clone_url, repo_dir, extra=['--depth=1', '--single-branch', '--quiet'], disable_lfs=False)
                            minimal_result = subprocess.run(minimal_cmd, capture_output=True, text=True, timeout=180, env=env)
                            
                            if minimal_result.returncode == 0:
                                logger.info(f"Successfully cloned {repo_full_name} with minimal clone after pack error")
                                strategy_used = 4  # Mark as successful
                            else:
                                raise GitServiceError(f"Git pack corruption (minimal clone failed): {repo_full_name} - {minimal_result.stderr}")
                        elif 'timeout' in error_msg or 'timed out' in error_msg:
                            raise GitServiceError(f"Network timeout while cloning: {repo_full_name}")
                        else:
                            raise GitServiceError(f"All clone strategies failed for {repo_full_name}. Last error: {result.stderr}")

                # Only fetch additional branches if not a bare clone
                if not (strategy_used and strategy_used == 3):  # Not bare clone
                    try:
                        fetch_result = subprocess.run(
                            ['git', 'fetch', '--all', '--prune'],
                            cwd=repo_dir,
                            capture_output=True,
                            text=True,
                            timeout=300  # Increased timeout
                        )
                        if fetch_result.returncode != 0:
                            logger.warning(f"Failed to fetch all branches for {repo_full_name}: {fetch_result.stderr}")
                            # Don't fail the entire clone for fetch issues
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Fetch timeout for {repo_full_name}, continuing with available branches")
                else:
                    logger.info(f"Bare clone used for {repo_full_name}, skipping branch fetch")
                
                # Store in cache
                self.cloned_repos[repo_full_name] = repo_dir
                
                logger.info(f"Successfully cloned {repo_full_name}")
                return repo_dir
                
            except subprocess.TimeoutExpired:
                raise GitServiceError(f"Timeout while cloning repository {repo_full_name}")
            except Exception as e:
                raise GitServiceError(f"Error cloning repository {repo_full_name}: {str(e)}")

    def _assert_safe_git_args(self, clone_url: str, repo_dir: str) -> None:
        """Additional safety checks to ensure args used in subprocess are controlled."""
        # No whitespace or control characters
        for s in (clone_url, repo_dir):
            if any(ch.isspace() for ch in s) or '\x00' in s:
                raise GitServiceError("Unsafe whitespace or null byte in arguments")

        # clone_url must be validated HTTPS or SSH GitHub URL
        if clone_url.startswith('https://'):
            parsed = urlparse(clone_url)
            host = (parsed.hostname or '').lower()
            if host != 'github.com':
                raise GitServiceError("Invalid clone URL host")
        elif clone_url.startswith('git@'):
            if not re.match(r'^git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?$', clone_url):
                raise GitServiceError("Invalid SSH clone URL format")
        else:
            raise GitServiceError("Unsupported clone URL scheme")

        # Ensure repo_dir is within the configured temp_dir
        temp_root = os.path.realpath(self.temp_dir)
        repo_real = os.path.realpath(repo_dir)
        if not repo_real.startswith(temp_root + os.sep):
            raise GitServiceError("Repository directory escapes temp directory")

    def _build_git_command(self, action: str, clone_url: str, repo_dir: str, extra: Optional[List[str]] = None, disable_lfs: bool = False) -> List[str]:
        """Construct a safe git command with whitelisted args."""
        if action != 'clone':
            raise GitServiceError("Unsupported git action")
        self._assert_safe_git_args(clone_url, repo_dir)
        base = ['git']
        if disable_lfs:
            base.extend(['-c', 'filter.lfs.clean=', '-c', 'filter.lfs.smudge=', '-c', 'filter.lfs.process=', '-c', 'filter.lfs.required=false'])
        cmd = base + ['clone']
        if extra:
            cmd.extend(extra)
        cmd.extend([clone_url, repo_dir])
        return cmd

    def _validate_repo_inputs(self, repo_url: str, repo_full_name: str) -> None:
        """Validate repository URL and full name to prevent unsafe command arguments."""
        # Validate full name like owner/repo with safe characters
        if not isinstance(repo_full_name, str) or '/' not in repo_full_name:
            raise GitServiceError("Invalid repository full name format")
        owner, repo = repo_full_name.split('/', 1)
        safe_pattern = re.compile(r'^[A-Za-z0-9_.-]+$')
        if not safe_pattern.match(owner) or not safe_pattern.match(repo):
            raise GitServiceError("Repository name contains invalid characters")

        # Validate URL scheme and host
        if repo_url.startswith('https://'):
            parsed = urlparse(repo_url)
            if parsed.scheme != 'https' or not parsed.netloc:
                raise GitServiceError("Invalid repository URL")
            host = (parsed.hostname or '').lower()
            if host != 'github.com':
                raise GitServiceError("Only github.com host is allowed for cloning")
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 2:
                raise GitServiceError("Repository URL path is invalid")
            repo_no_git = repo[:-4] if repo.endswith('.git') else repo
            expected_repo_names = {repo_no_git, f"{repo_no_git}.git"}
            if path_parts[0] != owner or path_parts[1] not in expected_repo_names:
                raise GitServiceError("Repository URL does not match repository full name")
        elif repo_url.startswith('git@'):
            # Strict SSH format: git@github.com:owner/repo(.git)?
            m = re.match(r'^git@github\.com:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(\.git)?$', repo_url)
            if not m:
                raise GitServiceError("Only GitHub SSH URLs are allowed (git@github.com:owner/repo[.git])")
            owner_m, repo_m, _ = m.groups()
            repo_no_git = repo[:-4] if repo.endswith('.git') else repo
            if owner_m != owner or repo_m != repo_no_git:
                raise GitServiceError("SSH URL does not match repository full name")
        else:
            raise GitServiceError("Unsupported repository URL scheme")

    def _sanitize_repo_dir_name(self, repo_full_name: str) -> str:
        """Create a safe directory name from owner/repo."""
        # First, replace directory separators
        flattened = repo_full_name.replace('/', '_').replace('\\', '_')
        
        # Remove any sequences of dots that could be used for path traversal
        # Replace multiple dots with single underscore
        flattened = re.sub(r'\.{2,}', '_', flattened)
        
        # Replace any remaining unsafe characters
        sanitized = re.sub(r'[^A-Za-z0-9_.-]', '_', flattened)
        
        # Collapse multiple consecutive underscores into single underscore
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Ensure no leading/trailing dots or underscores
        sanitized = sanitized.strip('._')
        
        # If empty after sanitization, use a default name
        if not sanitized:
            sanitized = 'repo'
            
        return sanitized

    def _build_authenticated_url(self, repo_url: str, github_token: Optional[str]) -> str:
        """Return a URL with embedded token for HTTPS GitHub URLs; otherwise the original URL."""
        if not github_token:
            return repo_url
        if repo_url.startswith('https://'):
            parsed = urlparse(repo_url)
            host = (parsed.hostname or '').lower()
            if host != 'github.com':
                return repo_url
            # Preserve port if present
            netloc_host = host
            if parsed.port:
                netloc_host = f"{host}:{parsed.port}"
            # Use GitHub-recommended basic auth format: username 'x-access-token' and token as password
            netloc = f"x-access-token:{github_token}@{netloc_host}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        return repo_url
    
    def get_repo_path(self, repo_full_name: str) -> str:
        """
        Get the path to a cloned repository
        
        Args:
            repo_full_name: Repository name in format "owner/repo"
            
        Returns:
            Path to repository directory
        """
        # Check cache first
        if repo_full_name in self.cloned_repos:
            repo_dir = self.cloned_repos[repo_full_name]
            if os.path.exists(repo_dir):
                return repo_dir
        
        # Check if repository exists on disk (even if not in cache)
        safe_dir_name = self._sanitize_repo_dir_name(repo_full_name)
        repo_dir = os.path.join(self.temp_dir, f"gitpulse_{safe_dir_name}")
        if os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, '.git')):
            # Add to cache for future use
            self.cloned_repos[repo_full_name] = repo_dir
            return repo_dir
        
        raise GitServiceError(f"Repository {repo_full_name} not cloned. Call clone_repository first.")
    
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
            
            # Debug: Log the working directory and repo path
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Repository path: {repo_path}")
            logger.info(f"Repository exists: {os.path.exists(repo_path)}")
            logger.info(f"Repository is git: {os.path.exists(os.path.join(repo_path, '.git'))}")
            
            # Build git log command - REMOVED --no-merges to get ALL commits including GitHub auto-commits
            cmd = ['git', 'log', '--all', '--pretty=format:%H|%an|%ae|%cn|%ce|%at|%ct|%s']
            
            # Add date filter if specified
            if since_date:
                since_timestamp = int(since_date.timestamp())
                cmd.extend(['--since', str(since_timestamp)])
            
            # Add limit if specified
            if max_commits:
                cmd.extend(['-n', str(max_commits)])
            
            # Execute git log
            logger.info(f"Executing git command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # Increased timeout to 5 minutes
                bufsize=0  # Unbuffered
            )
            
            logger.info(f"Git command return code: {result.returncode}")
            if result.stderr:
                logger.warning(f"Git command stderr: {result.stderr}")
            
            if result.returncode != 0:
                raise GitServiceError(f"Failed to fetch commits: {result.stderr}")
            
            # Parse output
            commits = []
            skipped_lines = 0
            total_lines = 0
            
            # Debug: Log the raw output length
            raw_output = result.stdout.strip()
            logger.info(f"Raw git output length: {len(raw_output)} characters")
            logger.info(f"Raw git output lines: {len(raw_output.split(chr(10)))}")
            
            for line in result.stdout.strip().split('\n'):
                total_lines += 1
                if not line.strip():
                    logger.debug(f"Empty line at position {total_lines}, skipping")
                    continue
                    
                parts = line.split('|')
                if len(parts) != 8:
                    logger.warning(f"Malformed commit line in {repo_full_name}: {line}")
                    logger.warning(f"Expected 8 parts, got {len(parts)}: {parts}")
                    skipped_lines += 1
                    continue
                
                sha, author_name, author_email, committer_name, committer_email, authored_timestamp, committed_timestamp, message = parts
                
                # Debug: Log unusual commit patterns
                if author_name != committer_name or author_email != committer_email:
                    logger.info(f"Commit {sha[:8]} has different author/committer: {author_name} vs {committer_name}")
                
                if 'github' in author_email.lower() or 'noreply' in author_email.lower():
                    logger.info(f"GitHub auto-commit detected: {sha[:8]} by {author_name} ({author_email})")
                
                commit = {
                    'sha': sha,
                    'author_name': author_name,
                    'author_email': author_email,
                    'committer_name': committer_name,
                    'committer_email': committer_email,
                    'authored_date': datetime.fromtimestamp(int(authored_timestamp), dt_timezone.utc),
                    'committed_date': datetime.fromtimestamp(int(committed_timestamp), dt_timezone.utc),
                    'message': message
                }
                
                commits.append(commit)
            
            # Debug: Log detailed parsing results
            logger.info(f"=== PARSING DEBUG for {repo_full_name} ===")
            logger.info(f"Total lines processed: {total_lines}")
            logger.info(f"Lines skipped (malformed): {skipped_lines}")
            logger.info(f"Commits successfully parsed: {len(commits)}")
            logger.info(f"Expected commits (from git): 127")
            logger.info(f"Missing commits: {127 - len(commits)}")
            logger.info(f"=== END PARSING DEBUG ===")
            
            logger.info(f"Fetched {len(commits)} commits from {repo_full_name} (skipped {skipped_lines} malformed lines out of {total_lines} total)")
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
                'authored_date': datetime.fromtimestamp(int(authored_timestamp), dt_timezone.utc),
                'committed_date': datetime.fromtimestamp(int(committed_timestamp), dt_timezone.utc),
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
                first_date = datetime.fromtimestamp(first_timestamp, dt_timezone.utc)
            
            if last_result.returncode == 0 and last_result.stdout.strip():
                last_timestamp = int(last_result.stdout.strip())
                last_date = datetime.fromtimestamp(last_timestamp, dt_timezone.utc)
            
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