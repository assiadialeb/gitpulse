# Quality Metrics Cleanup Fix

## Problem Description

When deleting an application or removing a repository from an application, the commits were properly deleted from MongoDB, but the Application Quality Metrics stored in the `developer_quality_metrics` collection were not being cleaned up.

## Root Cause

The cleanup functions in `analytics/services.py` were only deleting data from the following collections:
- `commits` (Commit model)
- `sync_logs` (SyncLog model) 
- `repository_stats` (RepositoryStats model)

However, they were not deleting data from the `developer_quality_metrics` collection where quality metrics are stored.

## Solution

### Modified Functions

1. **`cleanup_application_data(application_id)`** - Now includes:
   - Deletion of quality metrics for all repositories in the application
   - Fallback deletion by `application_id` if application is already deleted

2. **`cleanup_repository_data(repository_full_name)`** - Now includes:
   - Deletion of quality metrics for the specific repository

### Code Changes

```python
# Added to both cleanup functions:
from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client['gitpulse']
quality_collection = db['developer_quality_metrics']

# For application cleanup:
repository_names = list(application.repositories.values_list('github_repo_name', flat=True))
quality_result = quality_collection.delete_many({
    'repository': {'$in': repository_names}
})

# For repository cleanup:
quality_result = quality_collection.delete_many({
    'repository': repository_full_name
})
```

### Testing

Use the management command to test the cleanup:

```bash
# List all quality metrics
python manage.py test_quality_cleanup --list-all

# Test application cleanup
python manage.py test_quality_cleanup --application-id 1

# Test repository cleanup  
python manage.py test_quality_cleanup --repository "owner/repo"
```

## Verification

After the fix, when you:
1. Delete an application → All quality metrics for that application's repositories are deleted
2. Remove a repository from an application → All quality metrics for that specific repository are deleted

The cleanup is now complete and includes all MongoDB data related to the application or repository. 