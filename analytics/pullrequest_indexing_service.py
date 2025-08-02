"""
Pull Request indexing service for GitHub PRs
Fetches and processes GitHub Pull Requests using the Intelligent Indexing Service
"""
import logging
import requests
from datetime import datetime, timezone as dt_timezone
from django.utils import timezone
from typing import List, Dict, Optional
from mongoengine.errors import NotUniqueError

from .models import PullRequest
from .intelligent_indexing_service import IntelligentIndexingService

logger = logging.getLogger(__name__)


class PullRequestIndexingService:
    """Service for indexing GitHub Pull Requests with detailed information"""
    
    @staticmethod
    def fetch_pullrequests_from_github(owner: str, repo: str, token: str, 
                                     since: datetime, until: datetime) -> List[Dict]:
        """
        Fetch pull requests from GitHub API within the specified date range
        
        Args:
            owner: Repository owner
            repo: Repository name
            token: GitHub API token
            since: Start date (inclusive)
            until: End date (inclusive)
            
        Returns:
            List of pull request dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        pull_requests = []
        page = 1
        
        logger.info(f"Fetching pull requests for {owner}/{repo} from {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}")
        
        while True:
            params = {
                "per_page": 100,
                "page": page,
                "state": "all",  # Get both open and closed PRs
                "sort": "created",
                "direction": "desc"
            }
            
            try:
                response = requests.get(url, headers=headers, params=params)
                
                # Handle 403 Forbidden (no access to private repo)
                if response.status_code == 403:
                    logger.warning(f"Access denied to repository {repo_full_name} (403 Forbidden)")
                    return []  # Return empty list to indicate no access
                
                response.raise_for_status()
                
                batch = response.json()
                if not batch:
                    break
                
                # Filter PRs by date range (created_at)
                filtered_batch = []
                for pr in batch:
                    created_at_str = pr.get('created_at')
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            
                            # Ensure all dates are timezone-aware for comparison
                            if since.tzinfo is None:
                                since = timezone.make_aware(since)
                            if until.tzinfo is None:
                                until = timezone.make_aware(until)
                            if created_at.tzinfo is None:
                                created_at = timezone.make_aware(created_at)
                            
                            if since <= created_at <= until:
                                # Get detailed PR information
                                detailed_pr = PullRequestIndexingService._get_detailed_pr_info(
                                    owner, repo, pr['number'], token
                                )
                                if detailed_pr:
                                    filtered_batch.append(detailed_pr)
                            elif created_at < since:
                                # We've gone past our date range, stop fetching
                                logger.info(f"Reached PRs older than {since.strftime('%Y-%m-%d')}, stopping")
                                pull_requests.extend(filtered_batch)
                                return pull_requests
                        except ValueError as e:
                            logger.warning(f"Could not parse PR date {created_at_str}: {e}")
                            continue
                
                pull_requests.extend(filtered_batch)
                
                # If we got fewer than 100 items, we've reached the end
                if len(batch) < 100:
                    break
                
                page += 1
                
                # Protection against infinite loops
                if page > 50:  # Max 5000 PRs per batch
                    logger.warning(f"Hit maximum page limit (50) for {owner}/{repo} pull requests")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching pull requests from GitHub API: {e}")
                raise
        
        logger.info(f"Fetched {len(pull_requests)} pull requests for {owner}/{repo}")
        return pull_requests
    
    @staticmethod
    def _get_detailed_pr_info(owner: str, repo: str, pr_number: int, token: str) -> Optional[Dict]:
        """
        Get detailed PR information including review comments, commits, etc.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            token: GitHub API token
            
        Returns:
            Detailed PR info dictionary or None if error
        """
        try:
            # Get detailed PR info
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            pr_data = response.json()
            
            # Get additional PR stats
            # Get review comments count
            review_comments_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            review_resp = requests.get(review_comments_url, headers=headers)
            review_comments_count = 0
            if review_resp.status_code == 200:
                review_comments_count = len(review_resp.json())
            
            # Get regular comments count
            comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
            comments_resp = requests.get(comments_url, headers=headers)
            comments_count = 0
            if comments_resp.status_code == 200:
                comments_count = len(comments_resp.json())
            
            # Add computed fields
            pr_data['review_comments_count'] = review_comments_count
            pr_data['comments_count'] = comments_count
            pr_data['requested_reviewers_list'] = [r['login'] for r in pr_data.get('requested_reviewers', [])]
            pr_data['assignees_list'] = [a['login'] for a in pr_data.get('assignees', [])]
            pr_data['labels_list'] = [l['name'] for l in pr_data.get('labels', [])]
            
            return pr_data
            
        except Exception as e:
            logger.warning(f"Could not get detailed PR info for #{pr_number}: {e}")
            return None
    
    @staticmethod
    def process_pullrequests(pull_requests: List[Dict]) -> int:
        """
        Process and save pull requests to MongoDB
        
        Args:
            pull_requests: List of pull request dictionaries from GitHub API
            
        Returns:
            Number of pull requests processed
        """
        processed = 0
        
        for pr_data in pull_requests:
            try:
                # Extract required fields
                pr_number = pr_data.get('number')
                if not pr_number:
                    logger.warning("PR missing number, skipping")
                    continue
                
                # Parse dates
                created_at = None
                updated_at = None
                closed_at = None
                merged_at = None
                
                if pr_data.get('created_at'):
                    try:
                        created_at = datetime.fromisoformat(
                            pr_data['created_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse created_at for PR #{pr_number}")
                
                if pr_data.get('updated_at'):
                    try:
                        updated_at = datetime.fromisoformat(
                            pr_data['updated_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse updated_at for PR #{pr_number}")
                
                if pr_data.get('closed_at'):
                    try:
                        closed_at = datetime.fromisoformat(
                            pr_data['closed_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse closed_at for PR #{pr_number}")
                
                if pr_data.get('merged_at'):
                    try:
                        merged_at = datetime.fromisoformat(
                            pr_data['merged_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse merged_at for PR #{pr_number}")
                
                # Extract repository full name from PR data
                repo_full_name = pr_data.get('base', {}).get('repo', {}).get('full_name', '')
                
                # Create or update pull request (MongoEngine compatible)
                try:
                    # Try to get existing PR
                    pr = PullRequest.objects(
                        repository_full_name=repo_full_name,
                        number=pr_number
                    ).first()
                    
                    created = False
                    if not pr:
                        # Create new PR
                        pr = PullRequest(
                            repository_full_name=repo_full_name,
                            number=pr_number
                        )
                        created = True
                    
                    # Update PR fields
                    pr.title = pr_data.get('title', '')
                    pr.author = pr_data.get('user', {}).get('login', '') if pr_data.get('user') else ''
                    pr.created_at = created_at
                    pr.updated_at = updated_at
                    pr.closed_at = closed_at
                    pr.merged_at = merged_at
                    pr.state = pr_data.get('state', '')
                    pr.url = pr_data.get('html_url', '')
                    pr.labels = pr_data.get('labels_list', [])
                    pr.merged_by = pr_data.get('merged_by', {}).get('login', '') if pr_data.get('merged_by') else ''
                    pr.requested_reviewers = pr_data.get('requested_reviewers_list', [])
                    pr.assignees = pr_data.get('assignees_list', [])
                    pr.review_comments_count = pr_data.get('review_comments_count', 0)
                    pr.comments_count = pr_data.get('comments_count', 0)
                    pr.commits_count = pr_data.get('commits', 0)
                    pr.additions_count = pr_data.get('additions', 0)
                    pr.deletions_count = pr_data.get('deletions', 0)
                    pr.changed_files_count = pr_data.get('changed_files', 0)
                    pr.payload = pr_data
                    pr.save()
                    
                    if created:
                        processed += 1
                        logger.debug(f"Created new PR #{pr_number}")
                    else:
                        logger.debug(f"Updated existing PR #{pr_number}")
                        
                except Exception as e:
                    logger.warning(f"Error saving PR #{pr_number}: {e}")
                    continue
                    
            except Exception as e:
                logger.warning(f"Error processing PR {pr_data.get('number', 'unknown')}: {e}")
                continue
        
        logger.info(f"Processed {processed} new pull requests")
        return processed
    
    @staticmethod
    def index_pullrequests_for_repository(repository_id: int, user_id: int, batch_size_days: int = 365) -> Dict:
        """
        Index pull requests for a specific repository, simple et robuste.
        """
        try:
            from .github_token_service import GitHubTokenService
            from repositories.models import Repository
            from analytics.models import IndexingState
            from datetime import timedelta
            from django.utils import timezone
            import requests
            logger = logging.getLogger(__name__)

            repository = Repository.objects.get(id=repository_id)
            now = timezone.now()
            entity_type = 'pull_requests'
            state = IndexingState.objects(repository_id=repository_id, entity_type=entity_type).first()
            if state and state.last_indexed_at:
                since = state.last_indexed_at
            else:
                # No time limit - index all PRs from the beginning
                since = datetime(2010, 1, 1, tzinfo=dt_timezone.utc)  # GitHub was founded in 2008, but use 2010 as safe start
            until = now

            github_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
            if not github_token:
                github_token = GitHubTokenService._get_user_token(user_id)
                if not github_token:
                    github_token = GitHubTokenService._get_oauth_app_token()
            if not github_token:
                logger.warning(f"No GitHub token available for repository {repository.full_name}, skipping")
                return {'status': 'skipped', 'reason': 'No GitHub token available', 'repository_id': repository_id}

            # Vérifier la rate limit
            headers = {'Authorization': f'token {github_token}'}
            try:
                rate_response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
                if rate_response.status_code == 200:
                    rate_data = rate_response.json()
                    remaining = rate_data['resources']['core']['remaining']
                    reset_time = rate_data['resources']['core']['reset']
                    if remaining < 20:
                        next_run = datetime.fromtimestamp(reset_time, tz=dt_timezone.utc) + timedelta(minutes=5)
                        from django_q.models import Schedule
                        # Check if a retry task already exists for this repository
                        existing_retry = Schedule.objects.filter(
                            name=f'pullrequest_indexing_repo_{repository_id}_retry'
                        ).first()
                        
                        if existing_retry:
                            # Update existing retry schedule
                            existing_retry.func = 'analytics.tasks.index_pullrequests_intelligent_task'
                            existing_retry.args = [repository_id]
                            existing_retry.next_run = next_run
                            existing_retry.schedule_type = Schedule.ONCE
                            existing_retry.save()
                        else:
                            # Create new retry schedule
                            Schedule.objects.create(
                                func='analytics.tasks.index_pullrequests_intelligent_task',
                                args=[repository_id],
                                next_run=next_run,
                                schedule_type=Schedule.ONCE,
                                name=f'pullrequest_indexing_repo_{repository_id}_retry'
                            )
                        logger.warning(f"Rate limit reached, replanified for {next_run}")
                        return {'status': 'rate_limited', 'scheduled_for': next_run.isoformat()}
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding anyway")

            # Extraire owner et repo depuis full_name
            owner, repo = repository.full_name.split('/', 1)
            pull_requests = PullRequestIndexingService.fetch_pullrequests_from_github(
                owner=owner,
                repo=repo,
                token=github_token,
                since=since,
                until=until
            )
            processed = PullRequestIndexingService.process_pullrequests(pull_requests)

            if not state:
                state = IndexingState(repository_id=repository_id, entity_type=entity_type, repository_full_name=repository.full_name)
            state.last_indexed_at = until
            state.status = 'completed'
            state.save()

            logger.info(f"Indexed {processed} pull requests for {repository.full_name} from {since} to {until}")
            return {
                'status': 'success',
                'processed': processed,
                'repository_id': repository_id,
                'repository_full_name': repository.full_name,
                'date_range': {'since': since.isoformat(), 'until': until.isoformat()}
            }
        except Exception as e:
            logger.error(f"Error indexing pull requests for repository {repository_id}: {e}")
            raise 