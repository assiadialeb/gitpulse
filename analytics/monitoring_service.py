"""
Monitoring service for indexing health and performance
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from django.utils import timezone
from django_q.models import Task
from analytics.models import IndexingState
from repositories.models import Repository

logger = logging.getLogger(__name__)


class IndexingMonitoringService:
    """Service for monitoring indexing health and performance"""
    
    @staticmethod
    def get_indexing_health_report() -> Dict[str, Any]:
        """
        Get a comprehensive health report for all indexing operations
        
        Returns:
            Dictionary with health metrics
        """
        now = timezone.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)
        
        # Get all indexing states
        states = IndexingState.objects.all()
        
        # Get recent tasks
        recent_tasks = Task.objects.filter(
            func__startswith='analytics.tasks.index_',
            started__gte=one_hour_ago
        )
        
        # Calculate metrics
        total_repositories = Repository.objects.count()
        total_states = states.count()
        
        # Status breakdown
        status_counts = {}
        for state in states:
            status = state.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Error analysis
        error_states = states.filter(status='error')
        error_analysis = {}
        for state in error_states:
            error_msg = state.error_message or 'Unknown error'
            error_type = IndexingMonitoringService._categorize_error(error_msg)
            error_analysis[error_type] = error_analysis.get(error_type, 0) + 1
        
        # Performance metrics
        successful_tasks = recent_tasks.filter(success=True)
        failed_tasks = recent_tasks.filter(success=False)
        
        avg_execution_time = 0
        if successful_tasks.count() > 0:
            total_time = sum(
                (task.stopped - task.started).total_seconds() 
                for task in successful_tasks 
                if task.stopped and task.started
            )
            avg_execution_time = total_time / successful_tasks.count()
        
        # Rate limit analysis - we can't use contains on picklefield, so we'll count manually
        rate_limit_errors = 0
        for task in failed_tasks:
            if task.result and isinstance(task.result, str) and 'rate limit' in task.result.lower():
                rate_limit_errors += 1
        
        return {
            'timestamp': now.isoformat(),
            'overview': {
                'total_repositories': total_repositories,
                'total_indexing_states': total_states,
                'recent_tasks_1h': recent_tasks.count(),
                'successful_tasks_1h': successful_tasks.count(),
                'failed_tasks_1h': failed_tasks.count(),
            },
            'status_breakdown': status_counts,
            'error_analysis': error_analysis,
            'performance': {
                'avg_execution_time_seconds': round(avg_execution_time, 2),
                'success_rate_1h': round(
                    successful_tasks.count() / max(recent_tasks.count(), 1) * 100, 2
                ),
                'rate_limit_errors_1h': rate_limit_errors,
            },
            'alerts': IndexingMonitoringService._generate_alerts(
                status_counts, error_analysis, rate_limit_errors
            )
        }
    
    @staticmethod
    def _categorize_error(error_msg: str) -> str:
        """Categorize error messages into types"""
        error_lower = error_msg.lower()
        
        if any(pattern in error_lower for pattern in ['rate limit', '429']):
            return 'rate_limit'
        elif any(pattern in error_lower for pattern in ['not found', '404']):
            return 'not_found'
        elif any(pattern in error_lower for pattern in ['unauthorized', '401']):
            return 'unauthorized'
        elif any(pattern in error_lower for pattern in ['forbidden', '403']):
            return 'forbidden'
        elif any(pattern in error_lower for pattern in ['timeout', 'connection']):
            return 'network'
        elif any(pattern in error_lower for pattern in ['409 conflict']):
            return 'conflict'
        else:
            return 'other'
    
    @staticmethod
    def _generate_alerts(status_counts: Dict, error_analysis: Dict, rate_limit_errors: int) -> List[Dict]:
        """Generate alerts based on metrics"""
        alerts = []
        
        # High error rate alert
        total_states = sum(status_counts.values())
        error_count = status_counts.get('error', 0)
        if total_states > 0 and (error_count / total_states) > 0.1:  # >10% error rate
            alerts.append({
                'level': 'warning',
                'message': f'High error rate: {error_count}/{total_states} states in error',
                'type': 'high_error_rate'
            })
        
        # Rate limit alert
        if rate_limit_errors > 5:  # >5 rate limit errors in 1h
            alerts.append({
                'level': 'warning',
                'message': f'High rate limit errors: {rate_limit_errors} in the last hour',
                'type': 'rate_limit_issues'
            })
        
        # Stuck indexing alert
        stuck_count = status_counts.get('running', 0)
        if stuck_count > 3:  # >3 stuck indexing operations
            alerts.append({
                'level': 'warning',
                'message': f'Multiple stuck indexing operations: {stuck_count}',
                'type': 'stuck_indexing'
            })
        
        return alerts
    
    @staticmethod
    def get_repository_indexing_status(repository_id: int) -> Dict[str, Any]:
        """
        Get detailed indexing status for a specific repository
        
        Args:
            repository_id: Repository ID to check
            
        Returns:
            Dictionary with repository indexing status
        """
        try:
            repository = Repository.objects.get(id=repository_id)
        except Repository.DoesNotExist:
            return {'error': 'Repository not found'}
        
        states = IndexingState.objects.filter(repository_id=repository_id)
        
        status_info = {}
        for state in states:
            status_info[state.entity_type] = {
                'status': state.status,
                'total_indexed': state.total_indexed,
                'last_indexed_at': state.last_indexed_at.isoformat() if state.last_indexed_at else None,
                'last_run_at': state.last_run_at.isoformat() if state.last_run_at else None,
                'retry_count': state.retry_count,
                'error_message': state.error_message,
                'updated_at': state.updated_at.isoformat() if state.updated_at else None,
            }
        
        # Get recent tasks for this repository
        recent_tasks = Task.objects.filter(
            func__startswith='analytics.tasks.index_'
        ).order_by('-started')[:10]
        
        # Filter by repository_id manually since we can't use contains on picklefield
        filtered_tasks = []
        for task in recent_tasks:
            if task.args and len(task.args) > 0:
                task_repo_id = task.args[0]
                if isinstance(task_repo_id, list):
                    task_repo_id = task_repo_id[0]
                if task_repo_id == repository_id:
                    filtered_tasks.append(task)
        
        task_history = []
        for task in filtered_tasks:
            task_history.append({
                'func': task.func,
                'started': task.started.isoformat() if task.started else None,
                'stopped': task.stopped.isoformat() if task.stopped else None,
                'success': task.success,
                'attempt_count': task.attempt_count,
            })
        
        return {
            'repository': {
                'id': repository.id,
                'full_name': repository.full_name,
                'is_indexed': repository.is_indexed,
                'last_indexed': repository.last_indexed.isoformat() if repository.last_indexed else None,
            },
            'indexing_states': status_info,
            'recent_tasks': task_history,
        }
    
    @staticmethod
    def cleanup_stuck_indexing():
        """
        Clean up stuck indexing operations
        """
        now = timezone.now()
        one_hour_ago = now - timedelta(hours=1)
        
        # Find stuck indexing states (running for more than 1 hour)
        stuck_states = IndexingState.objects.filter(
            status='running',
            updated_at__lt=one_hour_ago
        )
        
        cleaned_count = 0
        for state in stuck_states:
            logger.warning(f"Cleaning up stuck indexing state: {state.repository_full_name} - {state.entity_type}")
            state.status = 'pending'
            state.retry_count = min(state.retry_count + 1, state.max_retries)
            state.save()
            cleaned_count += 1
        
        logger.info(f"Cleaned up {cleaned_count} stuck indexing states")
        return cleaned_count
