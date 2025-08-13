"""
CodeQL Indexing Service with intelligent state management
"""
import logging
import re
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import Dict, List, Optional

from .codeql_service import get_codeql_service_for_user
from .sanitization import assert_safe_repository_full_name
from .models import CodeQLVulnerability, IndexingState, SecurityHealthHistory
from .security_health_score_service import SecurityHealthScoreService

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
        logger.info("Starting CodeQL indexing for repository %s", repository_full_name)
        self._assert_safe_repository_full_name(repository_full_name)
        
        results = self._initialize_results(repository_id, repository_full_name)
        
        try:
            state = self._get_or_create_indexing_state(repository_id, repository_full_name)
            
            if not force_reindex and self._should_skip_indexing(state):
                return self._handle_skip_indexing(results, repository_full_name)
            
            state = self._start_indexing(state)
            
            codeql_service = self._get_codeql_service(repository_full_name)
            if not codeql_service:
                return self._handle_no_token(results, state, repository_full_name)
            
            alerts, fetch_success = self._fetch_alerts(codeql_service, repository_full_name)
            
            if not fetch_success:
                return self._handle_fetch_failure(results, state, alerts, repository_full_name)
            
            logger.info("Fetched %d CodeQL alerts for %s", len(alerts), repository_full_name)
            
            self._process_alerts(alerts, codeql_service, repository_full_name, results)
            
            self._cleanup_obsolete_vulnerabilities(repository_full_name, results)
            
            self._complete_indexing(state, results, repository_full_name)
            
        except Exception as e:
            self._handle_indexing_error(e, results, state, repository_full_name)
        
        results['completed_at'] = datetime.now(dt_timezone.utc).isoformat()
        return results

    def _initialize_results(self, repository_id: int, repository_full_name: str) -> Dict:
        """Initialize results dictionary"""
        return {
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

    def _handle_skip_indexing(self, results: Dict, repository_full_name: str) -> Dict:
        """Handle case where indexing should be skipped"""
        logger.info("Skipping CodeQL indexing for %s - recently indexed", repository_full_name)
        results['status'] = 'skipped'
        results['reason'] = 'Recently indexed'
        return results

    def _start_indexing(self, state: IndexingState) -> IndexingState:
        """Start indexing process"""
        state.status = 'running'
        state.last_run_at = datetime.now(dt_timezone.utc)
        state.save()
        return state

    def _get_codeql_service(self, repository_full_name: str):
        """Get CodeQL service for user"""
        return get_codeql_service_for_user(self.user_id, repository_full_name)

    def _handle_no_token(self, results: Dict, state: IndexingState, repository_full_name: str) -> Dict:
        """Handle case where no GitHub token is available"""
        error_msg = f"No GitHub token available for CodeQL analysis (repository: {repository_full_name})"
        logger.error(error_msg)
        results['status'] = 'error'
        results['errors'].append(error_msg)
        state.status = 'error'
        state.error_message = error_msg
        state.save()
        return results

    def _fetch_alerts(self, codeql_service, repository_full_name: str):
        """Fetch alerts from GitHub"""
        assert_safe_repository_full_name(repository_full_name)
        return codeql_service.fetch_all_codeql_alerts(repository_full_name)

    def _handle_fetch_failure(self, results: Dict, state: IndexingState, alerts: List, repository_full_name: str) -> Dict:
        """Handle fetch failure scenarios"""
        if len(alerts) == 0:
            if any('Unauthorized' in error for error in results.get('errors', [])):
                return self._handle_permission_denied(results, state, repository_full_name)
            else:
                return self._handle_not_available(results, state, repository_full_name)
        else:
            return self._handle_fetch_error(results, state, repository_full_name)

    def _handle_permission_denied(self, results: Dict, state: IndexingState, repository_full_name: str) -> Dict:
        """Handle permission denied case"""
        logger.error("Token permission issue for %s - CodeQL access denied", repository_full_name)
        results['status'] = 'permission_denied'
        results['reason'] = 'GitHub token does not have required permissions for CodeQL access'
        state.status = 'error'
        state.error_message = 'Token permission denied'
        state.save()
        return results

    def _handle_not_available(self, results: Dict, state: IndexingState, repository_full_name: str) -> Dict:
        """Handle CodeQL not available case"""
        logger.info("CodeQL not available/enabled for %s - marking as completed", repository_full_name)
        results['status'] = 'not_available'
        results['reason'] = 'CodeQL analysis not available or not enabled for this repository'
        state.status = 'completed'
        state.last_indexed_at = datetime.now(dt_timezone.utc)
        state.error_message = 'CodeQL not available'
        state.save()
        return results

    def _handle_fetch_error(self, results: Dict, state: IndexingState, repository_full_name: str) -> Dict:
        """Handle fetch error case"""
        error_msg = f"Failed to fetch CodeQL alerts from GitHub for {repository_full_name}"
        logger.error("Failed to fetch CodeQL alerts from GitHub for %s", repository_full_name)
        results['status'] = 'error'
        results['errors'].append(error_msg)
        state.status = 'error'
        state.error_message = error_msg
        state.retry_count += 1
        state.save()
        return results

    def _process_alerts(self, alerts: List, codeql_service, repository_full_name: str, results: Dict):
        """Process all alerts"""
        processed_alert_ids = []
        open_alert_ids = []
        
        for alert_data in alerts:
            try:
                vulnerability = codeql_service.process_codeql_alert(alert_data, repository_full_name)
                if not vulnerability:
                    continue
                
                assert_safe_repository_full_name(repository_full_name)
                existing = CodeQLVulnerability.objects(
                    repository_full_name=repository_full_name,
                    vulnerability_id=vulnerability.vulnerability_id
                ).first()
                
                if vulnerability.state == 'open':
                    open_alert_ids.append(vulnerability.vulnerability_id)

                if existing:
                    self._update_vulnerability(existing, vulnerability)
                    results['vulnerabilities_updated'] += 1
                else:
                    vulnerability.save()
                    results['vulnerabilities_new'] += 1
                
                processed_alert_ids.append(vulnerability.vulnerability_id)
                results['vulnerabilities_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing alert {alert_data.get('id')}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

    def _cleanup_obsolete_vulnerabilities(self, repository_full_name: str, results: Dict):
        """Remove obsolete vulnerabilities"""
        removed_count = self._remove_obsolete_vulnerabilities(repository_full_name, [])
        results['vulnerabilities_removed'] = removed_count

    def _complete_indexing(self, state: IndexingState, results: Dict, repository_full_name: str):
        """Complete indexing process"""
        state.status = 'completed'
        state.last_indexed_at = datetime.now(dt_timezone.utc)
        state.total_indexed = results['vulnerabilities_processed']
        state.error_message = None
        state.retry_count = 0
        state.save()
        
        logger.info(
            "CodeQL indexing completed for %s: %d new, %d updated, %d removed",
            repository_full_name,
            results['vulnerabilities_new'],
            results['vulnerabilities_updated'],
            results['vulnerabilities_removed'],
        )

    def _handle_indexing_error(self, e: Exception, results: Dict, state: IndexingState, repository_full_name: str):
        """Handle indexing error"""
        error_msg = f"CodeQL indexing failed for {repository_full_name}: {e}"
        logger.error(error_msg)
        results['status'] = 'error'
        results['errors'].append(error_msg)
        
        try:
            state.status = 'error'
            state.error_message = error_msg
            state.retry_count += 1
            state.save()
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            pass
    
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
            logger.info("Created new CodeQL indexing state for %s", repository_full_name)
        
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
            logger.info("Skipping CodeQL indexing - last indexed %s ago", time_since_last)
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

        # Keep severity/confidence in sync with GitHub (mapping may change over time)
        if getattr(new_data, 'severity', None) and new_data.severity != existing.severity:
            existing.severity = new_data.severity
        if getattr(new_data, 'confidence', None) and new_data.confidence != existing.confidence:
            existing.confidence = new_data.confidence

        # Keep rule metadata in sync (name/description/category/CWE)
        if getattr(new_data, 'rule_id', None):
            existing.rule_id = new_data.rule_id
        if getattr(new_data, 'rule_name', None):
            existing.rule_name = new_data.rule_name
        if getattr(new_data, 'rule_description', None):
            existing.rule_description = new_data.rule_description
        if getattr(new_data, 'category', None):
            existing.category = new_data.category
        if getattr(new_data, 'cwe_id', None):
            existing.cwe_id = new_data.cwe_id
        
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

        # Update commit metadata when provided
        if getattr(new_data, 'commit_sha', None):
            existing.commit_sha = new_data.commit_sha
        if getattr(new_data, 'fixed_commit_sha', None):
            existing.fixed_commit_sha = new_data.fixed_commit_sha
        if getattr(new_data, 'ref', None):
            existing.ref = new_data.ref
        
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
        # Validate input before querying
        assert_safe_repository_full_name(repository_full_name)
        # Find open vulnerabilities not in current GitHub alerts
        obsolete_vulns = CodeQLVulnerability.objects(
            repository_full_name=repository_full_name,
            state='open',
            vulnerability_id__nin=current_alert_ids
        )
        
        count = obsolete_vulns.count()
        if count > 0:
            logger.info("Removing %d obsolete vulnerabilities for %s", count, repository_full_name)
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
        # Validate repository_full_name to prevent NoSQL injection
        self._assert_safe_repository_full_name(repository_full_name)

        latest_vuln = CodeQLVulnerability.objects(
            repository_full_name=repository_full_name
        ).order_by('-analyzed_at').first()
        
        return latest_vuln.analyzed_at if latest_vuln else None
    
    def get_repository_security_metrics(self, repository_full_name: str, repository_id: int = None) -> Dict:
        """
        Get comprehensive security metrics for a repository including SHS
        
        Args:
            repository_full_name: Repository full name
            repository_id: Repository ID (optional, for SHS calculation)
            
        Returns:
            Dictionary with security metrics including SHS
        """
        try:
            # Validate repository_full_name to prevent NoSQL injection
            self._assert_safe_repository_full_name(repository_full_name)
            # Get repository KLOC
            from repositories.models import Repository
            try:
                repository = Repository.objects.get(full_name=repository_full_name)
                kloc = repository.kloc or 0.0
                if repository_id is None:
                    repository_id = repository.id
            except Repository.DoesNotExist:
                kloc = 0.0
                if repository_id is None:
                    repository_id = 0
            
            # Calculate SHS (always calculate, even for existing data)
            shs_service = SecurityHealthScoreService()
            shs_result = shs_service.calculate_shs(repository_full_name, repository_id, kloc)
            
            # Get latest vulnerabilities for additional info
            # Validate before querying to prevent NoSQL injection
            assert_safe_repository_full_name(repository_full_name)
            vulnerabilities = list(CodeQLVulnerability.objects(
                repository_full_name=repository_full_name
            ))
            
            if shs_result['status'] == 'not_available':
                return {
                    'shs_score': None,
                    'shs_display': 'Not available',
                    'shs_message': shs_result['message'],
                    'delta_shs': 0.0,
                    'total_vulnerabilities': 0,
                    'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
                    'latest_analysis': None
                }
            
            # Format SHS display
            if shs_result['shs_score'] is not None:
                shs_display = f"{shs_result['shs_score']}/100"
                # Show trend starting from the 2nd analysis (stable if delta == 0)
                # Validate before querying history collection as well
                assert_safe_repository_full_name(repository_full_name)
                history_count = SecurityHealthHistory.objects(
                    repository_full_name=repository_full_name
                ).count()
                if history_count >= 2:
                    delta_text = f" ({shs_result['delta_shs']:+.1f})"
                    shs_display += delta_text
            else:
                shs_display = "Not available"
            
            return {
                'shs_score': shs_result['shs_score'],
                'shs_display': shs_display,
                'shs_message': shs_result['message'],
                'delta_shs': shs_result['delta_shs'],
                'total_vulnerabilities': shs_result['total_vulnerabilities'],
                'severity_counts': shs_result['severity_counts'],
                'latest_analysis': self.get_latest_analysis_date(repository_full_name)
            }
            
        except Exception as e:
            logger.error("Error getting security metrics for %s: %s", repository_full_name, e)
            return {
                'shs_score': None,
                'shs_display': 'Error',
                'shs_message': f'Error: {str(e)}',
                'delta_shs': 0.0,
                'total_vulnerabilities': 0,
                'severity_counts': {'critical': 0, 'high': 0, 'medium': 0, 'low': 0},
                'latest_analysis': None
            }

    def _assert_safe_repository_full_name(self, repository_full_name: str) -> None:
        """Ensure repository_full_name matches expected pattern owner/repo with safe characters."""
        if not isinstance(repository_full_name, str):
            raise ValueError("repository_full_name must be a string")
        pattern = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
        if not pattern.match(repository_full_name):
            raise ValueError("Invalid repository_full_name format")
    
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