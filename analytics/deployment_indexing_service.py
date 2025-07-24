"""
Deployment indexing service for GitHub deployments
Fetches and processes GitHub deployments using the Intelligent Indexing Service
"""
import logging
import requests
from datetime import datetime
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
            token: GitHub API token
            since: Start date (inclusive)
            until: End date (inclusive)
            
        Returns:
            List of deployment dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/deployments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
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
                            from django.utils import timezone
                            if since.tzinfo is None:
                                since = timezone.make_aware(since)
                            if until.tzinfo is None:
                                until = timezone.make_aware(until)
                            if created_at.tzinfo is None:
                                created_at = timezone.make_aware(created_at)
                            
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
                if page > 50:  # Max 5000 deployments per batch
                    logger.warning(f"Hit maximum page limit (50) for {owner}/{repo} deployments")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching deployments from GitHub API: {e}")
                raise
        
        logger.info(f"Fetched {len(deployments)} deployments for {owner}/{repo}")
        return deployments
    
    @staticmethod
    def fetch_deployment_statuses(owner: str, repo: str, deployment_id: str, token: str) -> List[Dict]:
        """
        Fetch deployment statuses for a specific deployment
        
        Args:
            owner: Repository owner
            repo: Repository name
            deployment_id: Deployment ID
            token: GitHub API token
            
        Returns:
            List of deployment status dictionaries
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/deployments/{deployment_id}/statuses"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching deployment statuses for {deployment_id}: {e}")
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
                if created:
                    deployment.statuses = []  # Initialize statuses for new deployments
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
        Index deployments for a specific repository using intelligent indexing
        
        Args:
            repository_id: Repository ID
            user_id: User ID (owner of the repository)
            batch_size_days: Number of days per batch
            
        Returns:
            Dictionary with indexing results
        """
        try:
            from .github_token_service import GitHubTokenService
            from repositories.models import Repository
            
            # Get repository info
            repository = Repository.objects.get(id=repository_id)
            
            # Get GitHub token (simplified approach)
            github_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
            
            if not github_token:
                # Fallback to any available token
                github_token = GitHubTokenService._get_user_token(user_id)
                if not github_token:
                    github_token = GitHubTokenService._get_oauth_app_token()
            
            if not github_token:
                logger.warning(f"No GitHub token available for repository {repository.full_name}, skipping")
                return {
                    'status': 'skipped',
                    'reason': 'No GitHub token available',
                    'repository_id': repository_id,
                    'repository_full_name': repository.full_name
                }
            
            # Initialize intelligent indexing service
            indexing_service = IntelligentIndexingService(
                repository_id=repository_id,
                entity_type='deployments',
                github_token=github_token
            )
            
            # Run indexing batch
            result = indexing_service.index_batch(
                fetch_function=DeploymentIndexingService.fetch_deployments_from_github,
                process_function=DeploymentIndexingService.process_deployments,
                batch_size_days=batch_size_days
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error indexing deployments for repository {repository_id}: {e}")
            raise 