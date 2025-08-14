"""
Commit indexing service for GitHub commits with PR links
Fetches and processes GitHub commits using the Intelligent Indexing Service
"""
import logging
import requests
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import List, Dict, Optional
from mongoengine.errors import NotUniqueError
from django.utils import timezone

from .models import Commit, FileChange
from .intelligent_indexing_service import IntelligentIndexingService
from .commit_classifier import classify_commit_with_files, classify_commits_with_files_batch

logger = logging.getLogger(__name__)


class CommitIndexingService:
    """Service for indexing GitHub commits with PR links and file changes"""
    
    @staticmethod
    def fetch_commits_from_github(owner: str, repo: str, token: str, 
                                since: datetime, until: datetime) -> List[Dict]:
        """
        Fetch commits from GitHub API within the specified date range
        
        Args:
            owner: Repository owner
            repo: Repository name
            token: GitHub API token
            since: Start date (inclusive)
            until: End date (inclusive)
            
        Returns:
            List of commit dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        commits = []
        page = 1
        
        logger.info(f"Fetching commits for {owner}/{repo} from {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}")
        
        while True:
            params = {
                "per_page": 100,
                "page": page,
                "since": since.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "until": until.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            
            try:
                response = requests.get(url, headers=headers, params=params)
                
                # Handle 409 Conflict error specifically
                if response.status_code == 409:
                    logger.warning(f"409 Conflict for {owner}/{repo} - possible date range issue. Retrying with adjusted dates.")
                    
                    # Try multiple strategies to resolve the conflict
                    strategies = [
                        # Strategy 1: Skip the problematic date range entirely (most aggressive)
                        lambda: (since + timedelta(days=30), until),
                        # Strategy 2: Use a smaller date range
                        lambda: (since + timedelta(days=1), until - timedelta(days=1)),
                        # Strategy 3: Use a much smaller date range
                        lambda: (since + timedelta(days=7), until - timedelta(days=7)),
                        # Strategy 4: Skip this batch entirely by using recent dates
                        lambda: (timezone.now() - timedelta(days=1), timezone.now()),
                    ]
                    
                    conflict_resolved = False
                    for i, strategy in enumerate(strategies):
                        try:
                            adjusted_since, adjusted_until = strategy()
                            if adjusted_since < adjusted_until:
                                logger.info(f"409 Conflict - trying strategy {i+1} for {owner}/{repo}: {adjusted_since} to {adjusted_until}")
                                params["since"] = adjusted_since.strftime('%Y-%m-%dT%H:%M:%SZ')
                                params["until"] = adjusted_until.strftime('%Y-%m-%dT%H:%M:%SZ')
                                response = requests.get(url, headers=headers, params=params)
                                
                                if response.status_code != 409:
                                    conflict_resolved = True
                                    logger.info(f"409 Conflict resolved with strategy {i+1} for {owner}/{repo}")
                                    break
                        except Exception as e:
                            logger.warning(f"Strategy {i+1} failed for {owner}/{repo}: {e}")
                            continue
                    
                    if not conflict_resolved:
                        logger.error(f"Could not resolve 409 Conflict for {owner}/{repo} - skipping this batch")
                        # Return empty list to skip this problematic batch
                        return []
                    
                    # If we resolved the conflict but got no data, that's fine
                    if response.status_code == 200 and not response.json():
                        logger.info(f"409 Conflict resolved for {owner}/{repo} but no commits found in adjusted range")
                        return []
                
                response.raise_for_status()
                
                batch = response.json()
                if not batch:
                    break
                
                # For each commit, get detailed info including files
                detailed_commits = []
                for commit_summary in batch:
                    sha = commit_summary['sha']
                    
                    # Get detailed commit info including files
                    detail_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
                    detail_response = requests.get(detail_url, headers=headers)
                    detail_response.raise_for_status()
                    
                    detailed_commit = detail_response.json()
                    
                    # Check if commit is associated with a PR
                    pr_info = CommitIndexingService._get_pr_info_for_commit(
                        owner, repo, sha, token
                    )
                    if pr_info:
                        detailed_commit['pull_request_info'] = pr_info
                    
                    detailed_commits.append(detailed_commit)
                
                commits.extend(detailed_commits)
                
                # If we got fewer than 100 items, we've reached the end
                if len(batch) < 100:
                    break
                
                page += 1
                
                # Protection against infinite loops and rate limiting
                if page > 50:  # Max 5000 commits per batch
                    logger.warning(f"Hit maximum page limit (50) for {owner}/{repo} commits")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching commits from GitHub API: {e}")
                raise
        
        logger.info(f"Fetched {len(commits)} commits for {owner}/{repo}")
        return commits
    
    @staticmethod
    def _get_pr_info_for_commit(owner: str, repo: str, sha: str, token: str) -> Optional[Dict]:
        """
        Get PR information for a specific commit
        
        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA
            token: GitHub API token
            
        Returns:
            PR info dictionary or None if not found
        """
        try:
            # Check if commit is associated with a PR
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/pulls"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.groot-preview+json"  # Preview API for commit-PR association
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                prs = response.json()
                if prs:
                    # Return the first PR (usually there's only one)
                    pr = prs[0]
                    return {
                        'number': pr['number'],
                        'url': pr['html_url'],
                        'merged_at': pr.get('merged_at'),
                        'state': pr['state']
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not get PR info for commit {sha}: {e}")
            return None
    
    @staticmethod
    def process_commits(commits: List[Dict]) -> int:
        """
        Process and save commits to MongoDB
        
        Args:
            commits: List of commit dictionaries from GitHub API
            
        Returns:
            Number of commits processed
        """
        processed = 0

        # First pass: prepare batch classification inputs (message + filenames)
        classification_inputs: List[Dict] = []
        for commit_data in commits:
            commit_info = commit_data.get('commit', {})
            files_data = commit_data.get('files', [])
            message = commit_info.get('message', '')
            filenames = [file_data.get('filename', '') for file_data in files_data]
            classification_inputs.append({'message': message, 'files': filenames})

        # Batch classify commit types with fallback to Ollama (parallelized inside)
        try:
            logger.info(f"----------Classifying {len(classification_inputs)} commits (batch) via heuristic+Ollama fallback")
            batch_commit_types: List[str] = classify_commits_with_files_batch(classification_inputs)
        except Exception as _batch_err:
            # In case of any batch failure, fallback to per-commit classification
            logger.warning(f"----------Batch classification failed: {_batch_err}. Falling back to per-commit classification")
            batch_commit_types = []
            for item in classification_inputs:
                batch_commit_types.append(classify_commit_with_files(item.get('message', ''), item.get('files', [])))

        # Second pass: persist commits using precomputed types
        for idx, commit_data in enumerate(commits):
            try:
                # Extract required fields
                sha = commit_data.get('sha')
                if not sha:
                    logger.warning("Commit missing SHA, skipping")
                    continue
                
                # Parse commit data
                commit_info = commit_data.get('commit', {})
                author_info = commit_info.get('author', {})
                committer_info = commit_info.get('committer', {})
                
                # Parse dates
                authored_date = None
                committed_date = None
                
                if author_info.get('date'):
                    try:
                        authored_date = datetime.fromisoformat(
                            author_info['date'].replace('Z', '+00:00')
                        )
                        # Ensure timezone awareness
                        if authored_date.tzinfo is None:
                            authored_date = authored_date.replace(tzinfo=dt_timezone.utc)
                    except ValueError:
                        logger.warning(f"Could not parse authored_date for commit {sha}")
                
                if committer_info.get('date'):
                    try:
                        committed_date = datetime.fromisoformat(
                            committer_info['date'].replace('Z', '+00:00')
                        )
                        # Ensure timezone awareness
                        if committed_date.tzinfo is None:
                            committed_date = committed_date.replace(tzinfo=dt_timezone.utc)
                    except ValueError:
                        logger.warning(f"Could not parse committed_date for commit {sha}")
                
                # Extract repository full name from commit data
                repo_url = commit_data.get('html_url', '')
                repository_full_name = ''
                if repo_url:
                    # Extract owner/repo from URL like "https://github.com/owner/repo/commit/sha"
                    parts = repo_url.split('/')
                    if len(parts) >= 5:
                        repository_full_name = f"{parts[3]}/{parts[4]}"
                
                # Process file changes
                files_changed = []
                stats = commit_data.get('stats', {})
                files_data = commit_data.get('files', [])
                
                for file_data in files_data:
                    file_change = FileChange(
                        filename=file_data.get('filename', ''),
                        additions=file_data.get('additions', 0),
                        deletions=file_data.get('deletions', 0),
                        changes=file_data.get('changes', 0),
                        status=file_data.get('status', 'modified'),
                        patch=file_data.get('patch', '')
                    )
                    files_changed.append(file_change)
                
                # Extract PR information
                pull_request_number = None
                pull_request_url = None
                pull_request_merged_at = None
                
                pr_info = commit_data.get('pull_request_info')
                if pr_info:
                    pull_request_number = pr_info.get('number')
                    pull_request_url = pr_info.get('url')
                    if pr_info.get('merged_at'):
                        try:
                            pull_request_merged_at = datetime.fromisoformat(
                                pr_info['merged_at'].replace('Z', '+00:00')
                            )
                            # Ensure timezone awareness
                            if pull_request_merged_at.tzinfo is None:
                                pull_request_merged_at = pull_request_merged_at.replace(tzinfo=dt_timezone.utc)
                        except ValueError:
                            logger.warning(f"Could not parse merged_at for PR {pull_request_number}")
                
                # Commit type from batch classification (aligned by index)
                try:
                    commit_type = batch_commit_types[idx]
                except Exception:
                    # Safe fallback if out-of-range
                    filenames = [file_data.get('filename', '') for file_data in files_data]
                    commit_type = classify_commit_with_files(commit_info.get('message', ''), filenames)
                logger.debug(f"Commit {sha[:8]} classified as '{commit_type}'")
                
                # Create or update commit
                try:
                    commit = Commit.objects(sha=sha).first()
                    if not commit:
                        commit = Commit(
                            sha=sha,
                            repository_full_name=repository_full_name,
                            message=commit_info.get('message', ''),
                            author_name=author_info.get('name', ''),
                            author_email=author_info.get('email', ''),
                            committer_name=committer_info.get('name', ''),
                            committer_email=committer_info.get('email', ''),
                            authored_date=authored_date,
                            committed_date=committed_date,
                            additions=stats.get('additions', 0),
                            deletions=stats.get('deletions', 0),
                            total_changes=stats.get('total', 0),
                            files_changed=files_changed,
                            commit_type=commit_type,
                            pull_request_number=pull_request_number,
                            pull_request_url=pull_request_url,
                            pull_request_merged_at=pull_request_merged_at,
                            parent_shas=[parent['sha'] for parent in commit_data.get('parents', [])],
                            tree_sha=commit_data.get('commit', {}).get('tree', {}).get('sha', ''),
                            url=commit_data.get('html_url', '')
                        )
                        commit.save()
                        created = True
                    else:
                        created = False
                        commit.repository_full_name = repository_full_name
                        commit.message = commit_info.get('message', '')
                        commit.author_name = author_info.get('name', '')
                        commit.author_email = author_info.get('email', '')
                        commit.committer_name = committer_info.get('name', '')
                        commit.committer_email = committer_info.get('email', '')
                        commit.authored_date = authored_date
                        commit.committed_date = committed_date
                        commit.additions = stats.get('additions', 0)
                        commit.deletions = stats.get('deletions', 0)
                        commit.total_changes = stats.get('total', 0)
                        commit.files_changed = files_changed
                        commit.commit_type = commit_type
                        commit.pull_request_number = pull_request_number
                        commit.pull_request_url = pull_request_url
                        commit.pull_request_merged_at = pull_request_merged_at
                        commit.parent_shas = [parent['sha'] for parent in commit_data.get('parents', [])]
                        commit.tree_sha = commit_data.get('commit', {}).get('tree', {}).get('sha', '')
                        commit.url = commit_data.get('html_url', '')
                        commit.save()
                    
                    if created:
                        processed += 1
                        logger.debug(f"Created new commit {sha}")
                    else:
                        logger.debug(f"Updated existing commit {sha}")
                        
                except NotUniqueError:
                    logger.warning(f"Commit {sha} already exists, skipping")
                    continue
                    
            except Exception as e:
                logger.warning(f"Error processing commit {commit_data.get('sha', 'unknown')}: {e}")
                continue
        
        logger.info(f"Processed {processed} new commits")
        return processed
    
    @staticmethod
    def index_commits_for_repository(repository_id: int, user_id: int, 
                                   batch_size_days: int = None) -> Dict:
        """
        Index commits for a specific repository using intelligent indexing
        
        Args:
            repository_id: Repository ID
            user_id: User ID (owner of the repository)
            batch_size_days: Number of days per batch (None = adaptive sizing)
            
        Returns:
            Dictionary with indexing results
        """
        try:
            from .github_token_service import GitHubTokenService
            from repositories.models import Repository
            
            # Get repository info
            repository = Repository.objects.get(id=repository_id)
            
            # Get GitHub token
            github_token = GitHubTokenService.get_token_for_repository_access(
                user_id=user_id,
                repo_full_name=repository.full_name
            )
            
            if not github_token:
                raise Exception(f"No GitHub token available for repository {repository.full_name}")
            
            # Initialize intelligent indexing service
            indexing_service = IntelligentIndexingService(
                repository_id=repository_id,
                entity_type='commits',
                github_token=github_token
            )
            
            # Run indexing batch with adaptive sizing (batch_size_days=None triggers adaptive mode)
            result = indexing_service.index_batch(
                fetch_function=CommitIndexingService.fetch_commits_from_github,
                process_function=CommitIndexingService.process_commits,
                batch_size_days=batch_size_days  # None = adaptive, or specific value if provided
            )
            

            
            return result
            
        except Exception as e:
            logger.error(f"Error indexing commits for repository {repository_id}: {e}")
            raise 