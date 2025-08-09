# Troubleshooting Guide

## 🚨 Common Issues and Solutions

### 1. Function Not Defined Errors

**Error**: `Function analytics.tasks.release_indexing_all_apps_task is not defined`

**Cause**: Old tasks in Django-Q queue referencing renamed functions

**Solution**:
```bash
# Clean up old tasks
python manage.py cleanup_django_q

# Or use the specific cleanup command
python manage.py cleanup_old_tasks

# Restart Django-Q cluster if needed
python manage.py qcluster
```

### 2. Task Queue Issues

**Symptoms**: Tasks not executing, stuck in queue

**Solutions**:
```bash
# Check queue status
python manage.py shell -c "from django_q.models import Task; print(f'Total tasks: {Task.objects.count()}'); print(f'Failed tasks: {Task.objects.filter(success=False).count()}')"

# Clean failed tasks
python manage.py cleanup_django_q

# Restart cluster
python manage.py qcluster
```

### 3. Schedule Problems

**Symptoms**: Scheduled tasks not running at expected times

**Solutions**:
```bash
# Check scheduled tasks
python manage.py shell -c "from django_q.models import Schedule; [print(f'{s.name}: {s.func} | Next: {s.next_run}') for s in Schedule.objects.all()]"

# Recreate schedules
python manage.py setup_complete_indexing --time 02:00 --spread --force
```

## 🔧 Management Commands

### Cleanup Commands

```bash
# Comprehensive cleanup
python manage.py cleanup_django_q

# Clean old tasks only
python manage.py cleanup_old_tasks

# Clean failed tasks only
python manage.py cleanup_old_tasks --failed-only
```

### Setup Commands

```bash
# Setup complete indexing system
python manage.py setup_complete_indexing --time 02:00 --spread

# Setup repository indexing only
python manage.py setup_repository_indexing --global-task --time 02:00

# Force recreate all schedules
python manage.py setup_complete_indexing --time 02:00 --spread --force
```

## 📊 Monitoring Commands

### Check System Status

```bash
# Check all scheduled tasks
python manage.py shell -c "from django_q.models import Schedule; schedules = Schedule.objects.all(); print(f'Found {schedules.count()} schedules:'); [print(f'- {s.name}: {s.func}') for s in schedules]"

# Check task queue
python manage.py shell -c "from django_q.models import Task; tasks = Task.objects.all(); print(f'Total tasks: {tasks.count()}'); failed = Task.objects.filter(success=False); print(f'Failed tasks: {failed.count()}')"

# Check repository status
python manage.py shell -c "from repositories.models import Repository; repos = Repository.objects.filter(is_indexed=True); print(f'Indexed repositories: {repos.count()}'); [print(f'- {repo.full_name}') for repo in repos]"
```

### Test Individual Tasks

```bash
# Test commit indexing
python manage.py shell -c "from analytics.tasks import daily_indexing_all_repos_task; print(daily_indexing_all_repos_task())"

# Test release indexing
python manage.py shell -c "from analytics.tasks import release_indexing_all_repos_task; print(release_indexing_all_repos_task())"

# Test PR indexing
python manage.py shell -c "from analytics.tasks import fetch_all_pull_requests_task; print(fetch_all_pull_requests_task())"

# Test quality analysis
# Quality analysis task removed - metrics are calculated in real-time
# python manage.py shell -c "from analytics.tasks import quality_analysis_all_repos_task; print(quality_analysis_all_repos_task())"

# Test developer grouping
python manage.py shell -c "from analytics.tasks import group_developer_identities_task; print(group_developer_identities_task())"
```

## 🚀 Quick Fixes

### Reset Everything

```bash
# 1. Stop Django-Q cluster
# (Ctrl+C in the terminal running qcluster)

# 2. Clean up everything
python manage.py cleanup_django_q

# 3. Recreate schedules
python manage.py setup_complete_indexing --time 02:00 --spread --force

# 4. Start cluster
python manage.py qcluster
```

### Fix Specific Task

```bash
# If a specific task is failing, test it directly
python manage.py shell -c "from analytics.tasks import release_indexing_all_repos_task; result = release_indexing_all_repos_task(); print(f'Result: {result}')"

# If it works, the issue is in the queue - clean it
python manage.py cleanup_old_tasks
```

## 📋 Task Reference

### Current Task Functions

| Task | Function | Purpose |
|------|----------|---------|
| Commit Indexing | `daily_indexing_all_repos_task` | Index commits for all repos |
| PR Indexing | `fetch_all_pull_requests_task` | Fetch closed PRs |
| Release Indexing | `release_indexing_all_repos_task` | Index GitHub releases |
| ~~Quality Analysis~~ | ~~`quality_analysis_all_repos_task`~~ | ~~Analyze commit quality~~ (removed - calculated in real-time) |
| Developer Grouping | `group_developer_identities_task` | Group developer identities |

### Old Functions (Removed)

| Old Function | New Function |
|--------------|--------------|
| `release_indexing_all_apps_task` | `release_indexing_all_repos_task` |
| `daily_indexing_all_apps_task` | `daily_indexing_all_repos_task` |
| ~~`quality_analysis_all_apps_task`~~ | ~~`quality_analysis_all_repos_task`~~ (removed) |

## ⚠️ Prevention Tips

1. **Always use cleanup commands** when renaming functions
2. **Test tasks directly** before scheduling them
3. **Monitor the queue** regularly for failed tasks
4. **Use dry-run** when cleaning up to see what will be deleted
5. **Restart cluster** after major changes

## 🔍 Debug Commands

```bash
# Check Django-Q configuration
python manage.py shell -c "from django.conf import settings; print(settings.Q_CLUSTER)"

# Check MongoDB connection
python manage.py shell -c "from pymongo import MongoClient; client = MongoClient('localhost', 27017); print('MongoDB connected:', client.server_info())"

# Check task history
python manage.py shell -c "from django_q.models import Task; recent = Task.objects.order_by('-id')[:10]; [print(f'{t.func}: {t.success}') for t in recent]"
```

## 📞 Emergency Procedures

### If Nothing Works

1. **Stop all processes**
2. **Clean everything**:
   ```bash
   python manage.py cleanup_django_q
   ```
3. **Recreate from scratch**:
   ```bash
   python manage.py setup_complete_indexing --time 02:00 --spread --force
   ```
4. **Start fresh**:
   ```bash
   python manage.py qcluster
   ```

### If Tasks Keep Failing

1. **Check logs** for specific error messages
2. **Test functions directly** in Django shell
3. **Verify dependencies** (MongoDB, GitHub tokens)
4. **Clean and restart** the entire system 