"""
Release indexing service for GitHub releases
Fetches and processes GitHub Releases using the Intelligent Indexing Service
"""
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from mongoengine.errors import NotUniqueError

from .models import Release
from .intelligent_indexing_service import IntelligentIndexingService

logger = logging.getLogger(__name__)


class ReleaseIndexingService:
    """Service for indexing GitHub Releases with detailed information"""
    
    @staticmethod
    def fetch_releases_from_github(owner: str, repo: str, token: str, 
                                 since: datetime, until: datetime) -> List[Dict]:
        """
        Fetch releases from GitHub API within the specified date range
        
        Args:
            owner: Repository owner
            repo: Repository name
            token: GitHub API token
            since: Start date (inclusive)
            until: End date (inclusive)
            
        Returns:
            List of release dictionaries from GitHub API
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        releases = []
        page = 1
        
        logger.info(f"Fetching releases for {owner}/{repo} from {since.strftime('%Y-%m-%d')} to {until.strftime('%Y-%m-%d')}")
        
        while True:
            params = {
                "per_page": 100,
                "page": page
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
                
                # Filter releases by date range (published_at)
                filtered_batch = []
                for release in batch:
                    published_at_str = release.get('published_at')
                    if published_at_str:
                        try:
                            published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                            
                            # Ensure all dates are timezone-aware for comparison
                            from django.utils import timezone
                            if since.tzinfo is None:
                                since = timezone.make_aware(since)
                            if until.tzinfo is None:
                                until = timezone.make_aware(until)
                            if published_at.tzinfo is None:
                                published_at = timezone.make_aware(published_at)
                            
                            if since <= published_at <= until:
                                filtered_batch.append(release)
                            elif published_at < since:
                                # We've gone past our date range, stop fetching
                                logger.info(f"Reached releases older than {since.strftime('%Y-%m-%d')}, stopping")
                                releases.extend(filtered_batch)
                                return releases
                        except ValueError as e:
                            logger.warning(f"Could not parse release date {published_at_str}: {e}")
                            continue
                    else:
                        # Include draft releases without published_at
                        if release.get('draft'):
                            created_at_str = release.get('created_at')
                            if created_at_str:
                                try:
                                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                    
                                    # Check created_at for drafts
                                    from datetime import timezone
                                    if since.tzinfo is None:
                                        since = timezone.make_aware(since)
                                    if until.tzinfo is None:
                                        until = timezone.make_aware(until)
                                    if created_at.tzinfo is None:
                                        created_at = timezone.make_aware(created_at)
                                    
                                    if since <= created_at <= until:
                                        filtered_batch.append(release)
                                except ValueError as e:
                                    logger.warning(f"Could not parse draft release created_at {created_at_str}: {e}")
                                    continue
                
                releases.extend(filtered_batch)
                
                # If we got fewer than 100 items, we've reached the end
                if len(batch) < 100:
                    break
                
                page += 1
                
                # Protection against infinite loops
                if page > 20:  # Max 2000 releases per batch (releases are usually fewer)
                    logger.warning(f"Hit maximum page limit (20) for {owner}/{repo} releases")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching releases from GitHub API: {e}")
                raise
        
        logger.info(f"Fetched {len(releases)} releases for {owner}/{repo}")
        return releases
    
    @staticmethod
    def process_releases(releases: List[Dict]) -> int:
        """
        Process and save releases to MongoDB
        
        Args:
            releases: List of release dictionaries from GitHub API
            
        Returns:
            Number of releases processed
        """
        processed = 0
        
        for release_data in releases:
            try:
                # Extract required fields
                release_id = str(release_data.get('id'))
                if not release_id:
                    logger.warning("Release missing ID, skipping")
                    continue
                
                # Parse published_at
                published_at = None
                if release_data.get('published_at'):
                    try:
                        published_at = datetime.fromisoformat(
                            release_data['published_at'].replace('Z', '+00:00')
                        )
                    except ValueError:
                        logger.warning(f"Could not parse published_at for release {release_id}")
                
                # Extract repository full name from release data
                repo_url = release_data.get('html_url', '')
                repository_full_name = ''
                if repo_url:
                    # Extract owner/repo from URL like "https://github.com/owner/repo/releases/tag/v1.0.0"
                    parts = repo_url.split('/')
                    if len(parts) >= 5:
                        repository_full_name = f"{parts[3]}/{parts[4]}"
                
                # Process assets
                assets = []
                for asset in release_data.get('assets', []):
                    assets.append({
                        'id': asset.get('id'),
                        'name': asset.get('name'),
                        'size': asset.get('size'),
                        'download_count': asset.get('download_count'),
                        'browser_download_url': asset.get('browser_download_url'),
                        'created_at': asset.get('created_at'),
                        'updated_at': asset.get('updated_at')
                    })
                
                # Create or update release (MongoEngine compatible)
                try:
                    # Try to get existing release
                    release = Release.objects(release_id=release_id).first()
                    
                    created = False
                    if not release:
                        # Create new release
                        release = Release(release_id=release_id)
                        created = True
                    
                    # Update release fields
                    release.repository_full_name = repository_full_name
                    release.tag_name = release_data.get('tag_name', '')
                    release.name = release_data.get('name', '')
                    release.author = release_data.get('author', {}).get('login', '') if release_data.get('author') else ''
                    release.published_at = published_at
                    release.draft = release_data.get('draft', False)
                    release.prerelease = release_data.get('prerelease', False)
                    release.body = release_data.get('body', '')
                    release.html_url = release_data.get('html_url', '')
                    release.assets = assets
                    release.payload = release_data
                    release.save()
                    
                    if created:
                        processed += 1
                        logger.debug(f"Created new release {release_data.get('tag_name', release_id)}")
                    else:
                        logger.debug(f"Updated existing release {release_data.get('tag_name', release_id)}")
                        
                except Exception as e:
                    logger.warning(f"Error saving release {release_id}: {e}")
                    continue
                    
            except Exception as e:
                logger.warning(f"Error processing release {release_data.get('id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Processed {processed} new releases")
        return processed
    
    @staticmethod
    def index_releases_for_repository(repository_id: int, user_id: int, batch_size_days: int = 365) -> Dict:
        """
        Index releases for a specific repository, simple et robuste.
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
            entity_type = 'releases'
            state = IndexingState.objects(repository_id=repository_id, entity_type=entity_type).first()
            if state and state.last_indexed_at:
                since = state.last_indexed_at
            else:
                since = now - timedelta(days=730)
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
                        import datetime
                        from datetime import timezone as dt_timezone
                        next_run = datetime.datetime.fromtimestamp(reset_time, tz=dt_timezone.utc) + timedelta(minutes=5)
                        from django_q.models import Schedule
                        Schedule.objects.create(
                            func='analytics.tasks.index_releases_intelligent_task',
                            args=[repository_id],
                            next_run=next_run,
                            schedule_type=Schedule.ONCE,
                            name=f'release_indexing_repo_{repository_id}_retry'
                        )
                        logger.warning(f"Rate limit reached, replanified for {next_run}")
                        return {'status': 'rate_limited', 'scheduled_for': next_run.isoformat()}
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}, proceeding anyway")

            # Extraire owner et repo depuis full_name
            owner, repo = repository.full_name.split('/', 1)
            releases = ReleaseIndexingService.fetch_releases_from_github(
                owner=owner,
                repo=repo,
                token=github_token,
                since=since,
                until=until
            )
            processed = ReleaseIndexingService.process_releases(releases)

            if not state:
                state = IndexingState(repository_id=repository_id, entity_type=entity_type)
            state.last_indexed_at = until
            state.status = 'completed'
            state.save()

            logger.info(f"Indexed {processed} releases for {repository.full_name} from {since} to {until}")
            return {
                'status': 'success',
                'processed': processed,
                'repository_id': repository_id,
                'repository_full_name': repository.full_name,
                'date_range': {'since': since.isoformat(), 'until': until.isoformat()}
            }
        except Exception as e:
            logger.error(f"Error indexing releases for repository {repository_id}: {e}")
            raise 