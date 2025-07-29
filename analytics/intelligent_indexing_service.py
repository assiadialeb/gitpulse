"""
Intelligent indexing service for GitHub API entities
Manages indexing state and implements backfill strategy
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Tuple
from django.utils import timezone
from mongoengine import Q

from .models import IndexingState
from repositories.models import Repository

logger = logging.getLogger(__name__)


class IntelligentIndexingService:
    """
    Service for intelligent indexing of GitHub API entities
    Features:
    - Backfill strategy (newest first, then progressively older)
    - State persistence to avoid re-indexing
    - Date-based filtering instead of pagination
    - Rate limit protection
    """
    
    def __init__(self, repository_id: int, entity_type: str, github_token: str):
        """
        Initialize the intelligent indexing service
        
        Args:
            repository_id: Django Repository model ID
            entity_type: Type of entity to index ('deployments', 'pull_requests', 'releases', etc.)
            github_token: GitHub API token
        """
        self.repository_id = repository_id
        self.entity_type = entity_type
        self.github_token = github_token
        
        # Get repository information
        try:
            self.repository = Repository.objects.get(id=repository_id)
        except Repository.DoesNotExist:
            raise ValueError(f"Repository with ID {repository_id} not found")
        
        # Get or create indexing state
        self.state = self._get_or_create_state()
        
        logger.info(f"Initialized intelligent indexing for {self.repository.full_name} - {entity_type}")
    
    def _get_or_create_state(self) -> IndexingState:
        """Get or create indexing state for this repository and entity type"""
        try:
            state = IndexingState.objects.get(
                repository_id=self.repository_id,
                entity_type=self.entity_type
            )
        except IndexingState.DoesNotExist:
            state = IndexingState(
                repository_id=self.repository_id,
                repository_full_name=self.repository.full_name,
                entity_type=self.entity_type,
                status='pending'
            )
            state.save()
            logger.info(f"Created new indexing state for {self.repository.full_name} - {self.entity_type}")
        
        return state
    
    def should_index(self, min_interval_minutes: int = 1) -> bool:
        """
        Determine if indexing should proceed
        
        Args:
            min_interval_minutes: Minimum minutes between indexing runs
            
        Returns:
            True if indexing should proceed, False otherwise
        """
        # Don't index if already running
        if self.state.status == 'running':
            logger.info(f"Indexing already running for {self.repository.full_name} - {self.entity_type}")
            return False
        
        # Don't index too frequently
        if self.state.last_run_at:
            last_run_at = self.state.last_run_at
            # Ensure last_run_at is timezone-aware for comparison
            if last_run_at.tzinfo is None:
                last_run_at = timezone.make_aware(last_run_at)
            
            time_since_last = timezone.now() - last_run_at
            if time_since_last < timedelta(minutes=min_interval_minutes):
                logger.info(f"Too soon to re-index {self.repository.full_name} - {self.entity_type} "
                           f"(last run {time_since_last.total_seconds()/60:.1f} minutes ago)")
                return False
        
        # Don't retry failed tasks too many times
        if self.state.status == 'error' and self.state.retry_count >= self.state.max_retries:
            logger.warning(f"Max retries exceeded for {self.repository.full_name} - {self.entity_type}")
            return False
        
        return True
    
    def get_date_range_for_next_batch(self, batch_size_days: int = None) -> Tuple[datetime, datetime]:
        """
        Get the date range for the next batch to index
        
        Args:
            batch_size_days: Number of days per batch (uses state default if None)
            
        Returns:
            Tuple of (since_date, until_date) for the next batch
        """
        if batch_size_days is None:
            batch_size_days = self.state.batch_size_days
        
        now = timezone.now()
        
        if self.state.last_indexed_at is None:
            # First run: start with the most recent data
            until_date = now
            since_date = now - timedelta(days=batch_size_days)
            logger.info(f"First indexing batch for {self.repository.full_name} - {self.entity_type}: "
                       f"{since_date.strftime('%Y-%m-%d')} to {until_date.strftime('%Y-%m-%d')}")
        else:
            # Continue backfilling: go further back in history
            until_date = self.state.last_indexed_at
            
            # Ensure until_date is timezone-aware
            if until_date.tzinfo is None:
                until_date = timezone.make_aware(until_date)
            
            since_date = until_date - timedelta(days=batch_size_days)
            
            # No time limit - index all commits from the beginning of the repository
            
            logger.info(f"Backfill batch for {self.repository.full_name} - {self.entity_type}: "
                       f"{since_date.strftime('%Y-%m-%d')} to {until_date.strftime('%Y-%m-%d')}")
        
        return since_date, until_date
    
    def has_more_to_index(self, since_date: datetime) -> bool:
        """
        Check if there's more data to index after this batch
        
        Args:
            since_date: The oldest date in the current batch
            
        Returns:
            True if there's potentially more data to index
        """
        # No time limit - continue indexing until GitHub API returns no more data
        # We'll rely on the fetch function returning empty results to stop indexing
        return True
    
    def index_batch(self, 
                   fetch_function: Callable[[str, str, str, datetime, datetime], List[Dict]],
                   process_function: Callable[[List[Dict]], int],
                   batch_size_days: int = None) -> Dict[str, Any]:
        """
        Index a batch of entities using the provided functions
        
        Args:
            fetch_function: Function to fetch data from GitHub API
                           Signature: (owner, repo, token, since_date, until_date) -> List[Dict]
            process_function: Function to process and save the fetched data
                             Signature: (items: List[Dict]) -> int (number processed)
            batch_size_days: Number of days per batch
            
        Returns:
            Dictionary with indexing results
        """
        if not self.should_index():
            return {
                'status': 'skipped',
                'reason': 'Indexing should not proceed (already running, too recent, or max retries exceeded)'
            }
        
        # Update state to running
        self.state.status = 'running'
        self.state.last_run_at = timezone.now()
        if self.state.status == 'error':
            self.state.retry_count += 1
        self.state.save()
        
        try:
            # Get date range for this batch
            since_date, until_date = self.get_date_range_for_next_batch(batch_size_days)
            
            logger.info(f"Starting indexing batch for {self.repository.full_name} - {self.entity_type}")
            
            # Fetch data from GitHub API
            items = fetch_function(
                self.repository.owner_name,
                self.repository.repo_name,
                self.github_token,
                since_date,
                until_date
            )
            
            logger.info(f"Fetched {len(items)} {self.entity_type} items from GitHub API")
            
            # Process and save the data
            processed_count = process_function(items)
            
            logger.info(f"Processed {processed_count} {self.entity_type} items")
            
            # Update state with success
            self.state.last_indexed_at = since_date  # We've indexed up to this date
            self.state.total_indexed += processed_count
            self.state.status = 'completed'
            self.state.error_message = None
            self.state.retry_count = 0  # Reset retry count on success
            self.state.updated_at = timezone.now()
            self.state.save()
            
            # Check if there's more to index
            has_more = self.has_more_to_index(since_date)
            
            result = {
                'status': 'success',
                'processed': processed_count,
                'total_processed': self.state.total_indexed,
                'date_range': {
                    'since': since_date.isoformat(),
                    'until': until_date.isoformat()
                },
                'has_more': has_more,
                'repository': self.repository.full_name,
                'entity_type': self.entity_type
            }
            
            logger.info(f"Batch indexing completed successfully for {self.repository.full_name} - {self.entity_type}")
            return result
            
        except Exception as e:
            logger.error(f"Error during batch indexing for {self.repository.full_name} - {self.entity_type}: {str(e)}")
            
            # Update state with error
            self.state.status = 'error'
            self.state.error_message = str(e)
            self.state.updated_at = timezone.now()
            self.state.save()
            
            raise
    
    def reset_indexing_state(self):
        """Reset the indexing state (useful for debugging or re-indexing from scratch)"""
        self.state.last_indexed_at = None
        self.state.total_indexed = 0
        self.state.status = 'pending'
        self.state.error_message = None
        self.state.retry_count = 0
        self.state.updated_at = timezone.now()
        self.state.save()
        
        logger.info(f"Reset indexing state for {self.repository.full_name} - {self.entity_type}")
    
    def get_indexing_info(self) -> Dict[str, Any]:
        """Get current indexing information"""
        return {
            'repository': self.repository.full_name,
            'entity_type': self.entity_type,
            'status': self.state.status,
            'total_indexed': self.state.total_indexed,
            'last_indexed_at': self.state.last_indexed_at.isoformat() if self.state.last_indexed_at else None,
            'last_run_at': self.state.last_run_at.isoformat() if self.state.last_run_at else None,
            'retry_count': self.state.retry_count,
            'error_message': self.state.error_message
        } 