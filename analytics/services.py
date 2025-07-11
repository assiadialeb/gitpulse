"""
Services for MongoDB cleanup operations
"""
from typing import Dict
from .models import Commit, SyncLog, RepositoryStats


def cleanup_application_data(application_id: int) -> Dict:
    """
    Clean up all MongoDB data related to an application
    
    Args:
        application_id: The ID of the application to clean up
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'commits_deleted': 0,
        'sync_logs_deleted': 0,
        'repository_stats_deleted': 0,
        'total_deleted': 0
    }
    
    try:
        # Delete all commits for this application
        commits_deleted = Commit.objects(application_id=application_id).delete()
        results['commits_deleted'] = commits_deleted
        
        # Delete all sync logs for this application
        sync_logs_deleted = SyncLog.objects(application_id=application_id).delete()
        results['sync_logs_deleted'] = sync_logs_deleted
        
        # Delete all repository stats for this application
        repo_stats_deleted = RepositoryStats.objects(application_id=application_id).delete()
        results['repository_stats_deleted'] = repo_stats_deleted
        
        # Calculate total
        results['total_deleted'] = (
            results['commits_deleted'] + 
            results['sync_logs_deleted'] + 
            results['repository_stats_deleted']
        )
        
        return results
        
    except Exception as e:
        # Return error information
        results['error'] = str(e)
        return results 