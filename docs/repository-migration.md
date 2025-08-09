# Repository-Based Indexing Migration Guide

## 🔄 Overview

GitPulse has been migrated from an **application-centric** to a **repository-centric** indexing system. This change provides better performance, clearer ownership, and more flexible analytics.

## 📋 Key Changes

### Before (Application-Centric)
- Applications contained multiple repositories
- Indexing was done at the application level
- Tasks: `background_indexing_task(application_id, user_id)`
- Scheduled tasks referenced applications

### After (Repository-Centric)
- Repositories are indexed individually
- Each repository has its own indexing status
- Tasks: `background_indexing_task(repository_id, user_id)`
- Scheduled tasks reference repositories

## 🛠️ Migration Steps

### 1. Clean Up Old Schedules

```bash
# Check what old schedules exist
python manage.py cleanup_old_schedules --dry-run

# Delete old schedules
python manage.py cleanup_old_schedules
```

### 2. Set Up New Repository Indexing

**Option A: Global Task (Recommended)**
```bash
# Single task that processes all indexed repositories
python manage.py setup_repository_indexing --global-task --time 02:00
```

**Option B: Individual Tasks**
```bash
# Separate task for each repository (spreads load)
python manage.py setup_repository_indexing --time 02:00
```

### 3. Verify Setup

```bash
# List all scheduled tasks
python manage.py shell -c "
from django_q.models import Schedule
schedules = Schedule.objects.all()
print(f'Found {schedules.count()} scheduled tasks:')
for s in schedules:
    print(f'- {s.name}: {s.func}')
"
```

## 📊 New Task Functions

### Indexing Tasks
- `daily_indexing_all_repos_task()` - Index all repositories
- `background_indexing_task(repository_id, user_id)` - Index single repository

### Analytics Tasks
- `release_indexing_all_repos_task()` - Index releases for all repos
- ~~`quality_analysis_all_repos_task()`~~ - Quality analysis for all repos (removed - metrics calculated in real-time)
- `fetch_all_pull_requests_task()` - Fetch PRs for all repos

## 🎯 Benefits

### Performance
- **Parallel processing**: Each repository can be indexed independently
- **Better resource usage**: Failed indexing for one repo doesn't affect others
- **Selective indexing**: Only process repositories that need updates

### Flexibility
- **Per-repository control**: Enable/disable indexing per repository
- **User-based ownership**: Each user manages their own repositories
- **Cleaner metrics**: Repository-specific analytics

### Scalability
- **Horizontal scaling**: Easy to distribute tasks across workers
- **Load balancing**: Spread indexing across time slots
- **Memory efficiency**: Process one repository at a time

## ⚙️ Configuration Options

### Global Task Setup
```bash
# Basic setup at 2 AM
python manage.py setup_repository_indexing --global-task --time 02:00

# Custom time
python manage.py setup_repository_indexing --global-task --time 03:30

# Force recreate
python manage.py setup_repository_indexing --global-task --time 02:00 --force
```

### Individual Task Setup
```bash
# Spread tasks across the hour (recommended for many repos)
python manage.py setup_repository_indexing --time 02:00

# Force recreate all individual tasks
python manage.py setup_repository_indexing --time 02:00 --force
```

## 🔍 Monitoring

### Check Task Status
```bash
# View Django-Q cluster
python manage.py qmonitor

# Check scheduled tasks
python manage.py shell -c "
from django_q.models import Schedule
repo_tasks = Schedule.objects.filter(name__contains='repo')
print(f'Repository tasks: {repo_tasks.count()}')
for task in repo_tasks:
    print(f'- {task.name} (next: {task.next_run})')
"
```

### Repository Status
```bash
# Check indexed repositories
python manage.py shell -c "
from repositories.models import Repository
indexed = Repository.objects.filter(is_indexed=True)
print(f'Indexed repositories: {indexed.count()}')
for repo in indexed:
    print(f'- {repo.full_name} (owner: {repo.owner.username})')
"
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Function Not Defined Error
**Error**: `Function analytics.tasks.release_indexing_all_apps_task is not defined`

**Solution**: Update scheduled tasks
```bash
python manage.py cleanup_old_schedules
python manage.py setup_repository_indexing --global-task --time 02:00
```

#### 2. No Repositories Being Processed
**Symptoms**: Tasks run but no repositories are indexed

**Solution**: Check repository indexing status
```bash
python manage.py shell -c "
from repositories.models import Repository
total = Repository.objects.count()
indexed = Repository.objects.filter(is_indexed=True).count()
print(f'Total repositories: {total}')
print(f'Indexed repositories: {indexed}')
if indexed == 0:
    print('No repositories are marked as indexed!')
    print('Add repositories via /repositories/ and start indexing.')
"
```

#### 3. Task Arguments Error
**Error**: Task receives wrong arguments

**Solution**: Ensure tasks use repository_id, not application_id
```bash
# Check task signatures
python manage.py shell -c "
from analytics.tasks import background_indexing_task
import inspect
sig = inspect.signature(background_indexing_task)
print(f'Function signature: {sig}')
"
```

## 📝 Manual Operations

### Index Single Repository
```bash
python manage.py shell -c "
from repositories.models import Repository
from analytics.tasks import background_indexing_task
from django_q.tasks import async_task

repo = Repository.objects.get(id=3)  # Replace with your repo ID
task_id = async_task(
    'analytics.tasks.background_indexing_task',
    repo.id,
    repo.owner_id
)
print(f'Started indexing task: {task_id}')
"
```

### Test New Functions
```bash
# Test repository indexing
python manage.py shell -c "
from analytics.tasks import daily_indexing_all_repos_task
result = daily_indexing_all_repos_task()
print(f'Indexing result: {result}')
"

# Test release indexing
python manage.py shell -c "
from analytics.tasks import release_indexing_all_repos_task
result = release_indexing_all_repos_task()
print(f'Release indexing result: {result}')
"
```

## 📚 Next Steps

1. **Monitor the new system** for a few days
2. **Check repository metrics** at `/repositories/{id}/`
3. **Adjust scheduling** if needed based on load
4. **Add more repositories** through the UI
5. **Set up application aggregation** (planned feature)

## ✅ Verification Checklist

- [ ] Old schedules cleaned up
- [ ] New repository indexing scheduled
- [ ] All task functions use repository_id
- [ ] Repository detail pages show metrics
- [ ] Manual indexing works from UI
- [ ] Automatic indexing runs daily
- [ ] No "function not defined" errors in logs 