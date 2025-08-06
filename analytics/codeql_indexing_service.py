"""
CodeQL Indexing Service with intelligent state management
"""
import logging
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import Dict, List, Optional, Tuple

from .codeql_service import CodeQLService, get_codeql_service_for_user
from .models import CodeQLVulnerability, IndexingState

logger = logging.getLogger(__name__)


class CodeQLIndexingService:
    """Service for intelligent CodeQL vulnerability indexing"""
    
    def __init__(self, user_id: int):
        """
        Initialize CodeQL indexing service
        
        Args:
            user_id: User ID for GitHub token access
        """
        self.user_id = user_id
        self.entity_type = 'codeql_vulnerabilities'
        
    def index_codeql_for_repository(self, repository_id: int, repository_full_name: str,
                                   force_reindex: bool = False) -> Dict:
        """
        Index CodeQL vulnerabilities for a repository with intelligent state management
        
        Args:
            repository_id: Repository ID
            repository_full_name: Repository full name (owner/repo)
            force_reindex: Force complete reindexing
            
        Returns:
            Dictionary with indexing results
        """
        logger.info(f"Starting CodeQL indexing for repository {repository_full_name}")
        
        results = {
            'repository_id': repository_id,
            'repository_full_name': repository_full_name,
            'vulnerabilities_processed': 0,
            'vulnerabilities_new': 0,
            'vulnerabilities_updated': 0,
            'vulnerabilities_removed': 0,
            'status': 'success',
            'errors': [],
            'indexing_service': 'codeql',
            'started_at': datetime.now(dt_timezone.utc).isoformat()
        }
        
        try:
            # Get or create indexing state
            state = self._get_or_create_indexing_state(repository_id, repository_full_name)
            
            # Check if we should skip indexing
            if not force_reindex and self._should_skip_indexing(state):
                logger.info(f"Skipping CodeQL indexing for {repository_full_name} - recently indexed")
                results['status'] = 'skipped'
                results['reason'] = 'Recently indexed'
                return results
            
            # Update state to running
            state.status = 'running'
            state.last_run_at = datetime.now(dt_timezone.utc)
            state.save()
            
            # Get CodeQL service
            codeql_service = get_codeql_service_for_user(self.user_id)
            if not codeql_service:
                error_msg = f"No GitHub token available for CodeQL analysis (repository: {repository_full_name})"
                logger.error(error_msg)
                results['status'] = 'error'
                results['errors'].append(error_msg)
                state.status = 'error'
                state.error_message = error_msg
                state.save()
                return results
            
            # Fetch all alerts from GitHub
            alerts, fetch_success = codeql_service.fetch_all_codeql_alerts(repository_full_name)
            
            if not fetch_success:
                # Check if it's a "not available" case vs a real error
                if len(alerts) == 0:
                    # Check if it's a token permission issue or truly not available
                    if any('Unauthorized' in error for error in results.get('errors', [])):
                        logger.error(f"Token permission issue for {repository_full_name} - CodeQL access denied")
                        results['status'] = 'permission_denied'
                        results['reason'] = 'GitHub token does not have required permissions for CodeQL access'
                        state.status = 'error'
                        state.error_message = 'Token permission denied'
                        state.save()
                        return results
                    else:
                        # CodeQL likely not enabled on this repository
                        logger.info(f"CodeQL not available/enabled for {repository_full_name} - marking as completed")
                        results['status'] = 'not_available'
                        results['reason'] = 'CodeQL analysis not available or not enabled for this repository'
                        state.status = 'completed'  # Mark as completed so we don't keep retrying
                        state.last_indexed_at = datetime.now(dt_timezone.utc)
                        state.error_message = 'CodeQL not available'
                        state.save()
                        return results
                else:
                    error_msg = f"Failed to fetch CodeQL alerts from GitHub for {repository_full_name}"
                    logger.error(error_msg)
                    results['status'] = 'error'
                    results['errors'].append(error_msg)
                    state.status = 'error'
                    state.error_message = error_msg
                    state.retry_count += 1
                    state.save()
                    return results
            
            logger.info(f"Fetched {len(alerts)} CodeQL alerts for {repository_full_name}")
            
            # Process alerts
            processed_alert_ids = []
            
            for alert_data in alerts:
                try:
                    vulnerability = codeql_service.process_codeql_alert(alert_data, repository_full_name)
                    if not vulnerability:
                        continue
                    
                    # Check if vulnerability already exists
                    existing = CodeQLVulnerability.objects(
                        repository_full_name=repository_full_name,
                        vulnerability_id=vulnerability.vulnerability_id
                    ).first()
                    
                    if existing:
                        # Update existing vulnerability
                        self._update_vulnerability(existing, vulnerability)
                        results['vulnerabilities_updated'] += 1
                    else:
                        # Save new vulnerability
                        vulnerability.save()
                        results['vulnerabilities_new'] += 1
                    
                    processed_alert_ids.append(vulnerability.vulnerability_id)
                    results['vulnerabilities_processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing alert {alert_data.get('id')}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Remove vulnerabilities that are no longer in GitHub (if they were open)
            if processed_alert_ids:
                removed_count = self._remove_obsolete_vulnerabilities(
                    repository_full_name, processed_alert_ids
                )
                results['vulnerabilities_removed'] = removed_count
            
            # Update indexing state
            state.status = 'completed'
            state.last_indexed_at = datetime.now(dt_timezone.utc)
            state.total_indexed = results['vulnerabilities_processed']
            state.error_message = None
            state.retry_count = 0
            state.save()
            
            logger.info(f"CodeQL indexing completed for {repository_full_name}: "
                       f"{results['vulnerabilities_new']} new, "
                       f"{results['vulnerabilities_updated']} updated, "
                       f"{results['vulnerabilities_removed']} removed")
            
        except Exception as e:
            error_msg = f"CodeQL indexing failed for {repository_full_name}: {e}"
            logger.error(error_msg)
            results['status'] = 'error'
            results['errors'].append(error_msg)
            
            # Update state
            try:
                state.status = 'error'
                state.error_message = error_msg
                state.retry_count += 1
                state.save()
            except:
                pass  # Don't fail if we can't update state
        
        results['completed_at'] = datetime.now(dt_timezone.utc).isoformat()
        return results
    
    def _get_or_create_indexing_state(self, repository_id: int, repository_full_name: str) -> IndexingState:
        """Get or create indexing state for repository"""
        state = IndexingState.objects(
            repository_id=repository_id,
            entity_type=self.entity_type
        ).first()
        
        if not state:
            state = IndexingState(
                repository_id=repository_id,
                repository_full_name=repository_full_name,
                entity_type=self.entity_type,
                status='pending',
                batch_size_days=365  # CodeQL doesn't need daily batching
            )
            state.save()
            logger.info(f"Created new CodeQL indexing state for {repository_full_name}")
        
        return state
    
    def _should_skip_indexing(self, state: IndexingState) -> bool:
        """
        Determine if we should skip indexing based on state
        
        Args:
            state: Current indexing state
            
        Returns:
            True if indexing should be skipped
        """
        if not state.last_indexed_at:
            return False  # Never indexed before
        
        # Skip if indexed in the last 6 hours (CodeQL analysis doesn't change frequently)
        min_interval = timedelta(hours=6)
        time_since_last = datetime.now(dt_timezone.utc) - state.last_indexed_at
        
        if time_since_last < min_interval:
            logger.info(f"Skipping CodeQL indexing - last indexed {time_since_last} ago")
            return True
        
        return False
    
    def _update_vulnerability(self, existing: CodeQLVulnerability, new_data: CodeQLVulnerability) -> None:
        """
        Update existing vulnerability with new data
        
        Args:
            existing: Existing vulnerability in database
            new_data: New vulnerability data from API
        """
        # Update fields that might change
        existing.state = new_data.state
        existing.dismissed_reason = new_data.dismissed_reason
        existing.dismissed_comment = new_data.dismissed_comment
        existing.dismissed_at = new_data.dismissed_at
        existing.fixed_at = new_data.fixed_at
        existing.updated_at = new_data.updated_at or datetime.now(dt_timezone.utc)
        existing.payload = new_data.payload
        
        # Update message if it changed
        if new_data.message and new_data.message != existing.message:
            existing.message = new_data.message
        
        # Update location if it changed
        if new_data.file_path and new_data.file_path != existing.file_path:
            existing.file_path = new_data.file_path
            existing.start_line = new_data.start_line
            existing.end_line = new_data.end_line
            existing.start_column = new_data.start_column
            existing.end_column = new_data.end_column
        
        existing.save()
    
    def _remove_obsolete_vulnerabilities(self, repository_full_name: str, 
                                       current_alert_ids: List[str]) -> int:
        """
        Remove vulnerabilities that are no longer in GitHub but were marked as open
        
        Args:
            repository_full_name: Repository full name
            current_alert_ids: List of vulnerability IDs currently in GitHub
            
        Returns:
            Number of vulnerabilities removed
        """
        # Find open vulnerabilities not in current GitHub alerts
        obsolete_vulns = CodeQLVulnerability.objects(
            repository_full_name=repository_full_name,
            state='open',
            vulnerability_id__nin=current_alert_ids
        )
        
        count = obsolete_vulns.count()
        if count > 0:
            logger.info(f"Removing {count} obsolete vulnerabilities for {repository_full_name}")
            obsolete_vulns.delete()
        
        return count
    
    def get_latest_analysis_date(self, repository_full_name: str) -> Optional[datetime]:
        """
        Get the date of the latest CodeQL analysis for a repository
        
        Args:
            repository_full_name: Repository full name
            
        Returns:
            Latest analysis date or None if no analysis found
        """
        latest_vuln = CodeQLVulnerability.objects(
            repository_full_name=repository_full_name
        ).order_by('-analyzed_at').first()
        
        return latest_vuln.analyzed_at if latest_vuln else None
    
    def get_repository_security_metrics(self, repository_full_name: str) -> Dict:
        """
        Get comprehensive security metrics for a repository
        
        Args:
            repository_full_name: Repository full name
            
        Returns:
            Dictionary with security metrics
        """
        # Get all vulnerabilities for this repository
        vulnerabilities = list(CodeQLVulnerability.objects(
            repository_full_name=repository_full_name
        ))
        
        if not vulnerabilities:
            return {
                'level': 'safe',
                'level_display': 'Safe',
                'total_vulnerabilities': 0,
                'open_vulnerabilities': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0,
                'low_count': 0,
                'categories': {},
                'trend': 'stable',
                'last_analysis': None
            }
        
        # Use CodeQL service to calculate metrics
        codeql_service = CodeQLService()
        metrics = codeql_service.calculate_security_level(vulnerabilities)
        
        # Add additional metrics
        metrics['last_analysis'] = self.get_latest_analysis_date(repository_full_name)
        metrics['open_vulnerabilities'] = len([v for v in vulnerabilities if v.state == 'open'])
        
        return metrics
    
    def should_reindex(self, repository_full_name: str, force: bool = False) -> bool:
        """
        Determine if a repository should be reindexed
        
        Args:
            repository_full_name: Repository full name
            force: Force reindexing regardless of timing
            
        Returns:
            True if repository should be reindexed
        """
        if force:
            return True
        
        # Check last analysis date
        last_analysis = self.get_latest_analysis_date(repository_full_name)
        if not last_analysis:
            return True  # Never analyzed
        
        # Reindex if last analysis was more than 24 hours ago
        return (datetime.now(dt_timezone.utc) - last_analysis) > timedelta(days=1)


def get_codeql_indexing_service_for_user(user_id: int) -> CodeQLIndexingService:
    """
    Get CodeQL indexing service instance for a user
    
    Args:
        user_id: User ID
        
    Returns:
        CodeQLIndexingService instance
    """
    return CodeQLIndexingService(user_id)