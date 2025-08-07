"""
Deployment indexing service for GitHub deployments
Fetches and processes GitHub deployments using the Intelligent Indexing Service
"""
import logging
import requests
import time
from datetime import datetime, timezone as dt_timezone
from typing import List, Dict, Optional
from mongoengine.errors import NotUniqueError

from .models import Deployment
from .intelligent_indexing_service import IntelligentIndexingService

logger = logging.getLogger(__name__)


class DeploymentIndexingService:
    """Service for indexing GitHub deployments"""
    
    @staticmethod
    def fetch_deployments_from_github(owner: str, repo: str, token: str, 
                                    since: datetime, until: datetime) -> List[Dict]:
        """
        Fetch deployments from GitHub API within the specified date range
        
        Args:
            owner: Repository owner
            repo: Repository name
            token: GitHub API token (can be None for public repos)
            since: Start date (inclusive)
            until: End date (inclusive)
            
        Returns:
            List of deployment dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/deployments"
        
        # For public repos, we can fetch without authentication
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        
        deployments = []
        page = 1
        
        logger.info(f"Fetching deployments for {owner}/{repo} from {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}")
        
        while True:
            params = {
                "per_page": 100,
                "page": page,
                # Note: GitHub API doesn't support direct date filtering for deployments
                # We'll filter after fetching
            }
            
            try:
                response = requests.get(url, headers=headers, params=params)
                
                # Handle 403 Forbidden (no access to private repo)
                if response.status_code == 403:
                    logger.warning(f"Access denied to repository {owner}/{repo} (403 Forbidden)")
                    return []  # Return empty list to indicate no access
                
                response.raise_for_status()
                
                batch = response.json()
                if not batch:
                    break
                
                # Filter deployments by date range
                filtered_batch = []
                for deployment in batch:
                    created_at_str = deployment.get('created_at')
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            
                            # Ensure all dates are timezone-aware for comparison
                            if since.tzinfo is None:
                                since = since.replace(tzinfo=dt_timezone.utc)
                            if until.tzinfo is None:
                                until = until.replace(tzinfo=dt_timezone.utc)
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=dt_timezone.utc)
                            
                            if since <= created_at <= until:
                                filtered_batch.append(deployment)
                            elif created_at < since:
                                # We've gone past our date range, stop fetching
                                logger.info(f"Reached deployments older than {since.strftime('%Y-%m-%d')}, stopping")
                                deployments.extend(filtered_batch)
                                return deployments
                        except ValueError as e:
                            logger.warning(f"Could not parse deployment date {created_at_str}: {e}")
                            continue
                
                deployments.extend(filtered_batch)
                
                # If we got fewer than 100 items, we've reached the end
                if len(batch) < 100:
                    break
                
                page += 1
                
                # Protection against infinite loops
                if page > 20:  # Max 2000 deployments per batch
                    logger.warning(f"Hit maximum page limit (20) for {owner}/{repo} deployments")
                    break
                
                # Rate limit protection - pause between pages
                time.sleep(0.1)  # 100ms pause between pages
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching deployments from GitHub API: {e}")
                raise
        
        logger.info(f"Fetched {len(deployments)} deployments for {owner}/{repo}")
        return deployments
    
    @staticmethod
    def fetch_deployment_statuses(owner: str, repo: str, deployment_id: str, token: str = None) -> List[Dict]:
        """
        Fetch deployment statuses from GitHub API
        
        Args:
            owner: Repository owner
            repo: Repository name
            deployment_id: Deployment ID
            token: GitHub API token (can be None for public repos)
            
        Returns:
            List of deployment status dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/deployments/{deployment_id}/statuses"
        
        # For public repos, we can fetch without authentication
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        
        try:
            response = requests.get(url, headers=headers)
            
            # Handle 403 Forbidden (no access to private repo)
            if response.status_code == 403:
                logger.warning(f"Access denied to deployment statuses for {owner}/{repo} (403 Forbidden)")
                return []
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching deployment statuses: {e}")
            return []
    
    @staticmethod
    def process_deployments(deployments: List[Dict]) -> int:
        """
        Process and save deployments to MongoDB
        
        Args:
            deployments: List of deployment dictionaries from GitHub API
            
        Returns:
            Number of deployments processed
        """
        processed = 0
        
        for deployment_data in deployments:
            try:
                # Extract required fields
                deployment_id = str(deployment_data.get('id'))
                if not deployment_id:
                    logger.warning("Deployment missing ID, skipping")
                    continue
                
                # Parse created_at and updated_at
                created_at = None
                updated_at = None
                
                if deployment_data.get('created_at'):
                    try:
                        created_at = datetime.fromisoformat(
                            deployment_data['created_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse created_at for deployment {deployment_id}")
                
                if deployment_data.get('updated_at'):
                    try:
                        updated_at = datetime.fromisoformat(
                            deployment_data['updated_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse updated_at for deployment {deployment_id}")
                
                # Extract repository full name from the URL or use a placeholder
                repo_url = deployment_data.get('repository_url', '')
                repository_full_name = ''
                if repo_url:
                    # Extract owner/repo from URL like "https://api.github.com/repos/owner/repo"
                    parts = repo_url.split('/')
                    if len(parts) >= 2:
                        repository_full_name = f"{parts[-2]}/{parts[-1]}"
                
                # Create or update deployment (MongoEngine compatible)
                # Try to get existing deployment
                deployment = Deployment.objects(deployment_id=deployment_id).first()
                
                created = False
                if not deployment:
                    # Create new deployment
                    deployment = Deployment(deployment_id=deployment_id)
                    created = True
                
                # Update deployment fields
                deployment.repository_full_name = repository_full_name
                deployment.environment = deployment_data.get('environment', '')
                deployment.creator = deployment_data.get('creator', {}).get('login', '') if deployment_data.get('creator') else ''
                deployment.created_at = created_at
                deployment.updated_at = updated_at
                deployment.payload = deployment_data.get('payload', {})
                
                # Fetch deployment statuses (refresh logic: new/missing, non-terminal, or metadata changed)
                refresh_needed = created or not deployment.statuses
                if not refresh_needed:
                    try:
                        last_state = str((deployment.statuses or [{}])[-1].get('state', '')).lower()
                    except Exception:
                        last_state = ''
                    non_terminal_states = {'pending', 'in_progress', 'queued', 'waiting'}
                    if last_state in non_terminal_states:
                        refresh_needed = True
                    # Refresh if GitHub updated_at changed
                    if not refresh_needed and updated_at and (getattr(deployment, 'updated_at', None) != updated_at):
                        refresh_needed = True

                if refresh_needed:
                    try:
                        # Extract owner and repo from repository_full_name
                        if repository_full_name and '/' in repository_full_name:
                            owner, repo = repository_full_name.split('/')
                            
                            # Try to get user token for better permissions
                            user_token = None
                            try:
                                from allauth.socialaccount.models import SocialToken, SocialApp
                                from django.contrib.auth.models import User
                                
                                # Get first user with a token
                                social_app = SocialApp.objects.filter(provider='github').first()
                                if social_app:
                                    social_token = SocialToken.objects.filter(app=social_app).first()
                                    if social_token:
                                        user_token = social_token.token
                                        logger.debug(f"Using user token for deployment statuses")
                            except Exception as e:
                                logger.debug(f"Could not get user token: {e}")
                            
                            # Try with user token first, then without token for public repos
                            statuses = []
                            if user_token:
                                try:
                                    statuses = DeploymentIndexingService.fetch_deployment_statuses(
                                        owner, repo, deployment_id, user_token
                                    )
                                    logger.debug(f"Fetched {len(statuses)} statuses with user token for deployment {deployment_id}")
                                except Exception as e:
                                    logger.debug(f"Failed to fetch statuses with user token: {e}")
                            
                            # If no statuses found with user token, try without token (for public repos)
                            if not statuses:
                                try:
                                    statuses = DeploymentIndexingService.fetch_deployment_statuses(
                                        owner, repo, deployment_id, None
                                    )
                                    logger.debug(f"Fetched {len(statuses)} statuses without token for deployment {deployment_id}")
                                except Exception as e:
                                    logger.debug(f"Failed to fetch statuses without token: {e}")
                            
                            deployment.statuses = statuses
                            logger.debug(f"Fetched {len(statuses)} statuses for deployment {deployment_id}")
                        else:
                            deployment.statuses = []
                            logger.warning(f"Could not extract owner/repo from {repository_full_name}")
                    except Exception as e:
                        logger.warning(f"Error fetching statuses for deployment {deployment_id}: {e}")
                        deployment.statuses = []
                
                deployment.save()
                
                if created:
                    processed += 1
                    logger.debug(f"Created new deployment {deployment_id}")
                else:
                    logger.debug(f"Updated existing deployment {deployment_id}")
                    
            except Exception as e:
                logger.warning(f"Error processing deployment {deployment_data.get('id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Processed {processed} new deployments")
        return processed
    
    @staticmethod
    def index_deployments_for_repository(repository_id: int, user_id: int, 
                                       batch_size_days: int = 30) -> Dict:
        """
        Index deployments for a specific repository, optimized version.
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
            entity_type = 'deployments'
            state = IndexingState.objects(repository_id=repository_id, entity_type=entity_type).first()
            
            # Optimized date range - use intelligent indexing service
            from .intelligent_indexing_service import IntelligentIndexingService
            
            indexing_service = IntelligentIndexingService(
                repository_id=repository_id,
                entity_type=entity_type,
                github_token=github_token
            )
            
            since, until = indexing_service.get_indexing_date_range()
            
            logger.info(f"Indexing period: {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}")

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
                rate_limit_response = requests.get('https://api.github.com/rate_limit', headers=headers)
                if rate_limit_response.status_code == 200:
                    rate_limit_data = rate_limit_response.json()
                    core_remaining = rate_limit_data['resources']['core']['remaining']
                    core_limit = rate_limit_data['resources']['core']['limit']
                    reset_time = rate_limit_data['resources']['core']['reset']
                    
                    logger.info(f"Rate limit: {core_remaining}/{core_limit} remaining")
                    
                    # If we have less than 100 requests remaining, schedule for later
                    if core_remaining < 100:
                        from datetime import datetime
                        next_run = datetime.fromtimestamp(reset_time)
                        logger.warning(f"Rate limit nearly exhausted, scheduling for {next_run}")
                        
                        return {'status': 'rate_limited', 'scheduled_for': next_run.isoformat()}
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding anyway")

            # Extraire owner et repo depuis full_name
            owner, repo = repository.full_name.split('/', 1)
            deployments = DeploymentIndexingService.fetch_deployments_from_github(
                owner=owner,
                repo=repo,
                token=github_token,
                since=since,
                until=until
            )
            processed = DeploymentIndexingService.process_deployments(deployments)

            if not state:
                state = IndexingState(repository_id=repository_id, entity_type=entity_type, repository_full_name=repository.full_name)
            state.last_indexed_at = until
            state.status = 'completed'
            state.save()

            logger.info(f"Indexed {processed} deployments for {repository.full_name} from {since} to {until}")
            return {
                'status': 'success',
                'processed': processed,
                'repository_id': repository_id,
                'repository_full_name': repository.full_name,
                'date_range': {'since': since.isoformat(), 'until': until.isoformat()}
            }
        except Exception as e:
            logger.error(f"Error indexing deployments for repository {repository_id}: {e}")
            raise 