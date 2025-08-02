# Management Commands Reference

This document provides a complete reference for all management commands available in GitPulse.

## 🔄 Automatic Indexing Commands

### Setup Commands

#### `setup_auto_indexing`
Set up automatic daily indexing for all applications.

```bash
# Basic setup (2 AM UTC default)
python manage.py setup_auto_indexing

# Custom time
python manage.py setup_auto_indexing --time 03:00

# Force recreate all schedules
python manage.py setup_auto_indexing --time 02:00 --force
```

**Options:**
- `--time HH:MM`: Set custom time (24-hour format)
- `--force`: Recreate existing schedules

**Examples:**
```bash
# Set up indexing at 2 AM UTC
python manage.py setup_auto_indexing

# Set up indexing at 3:30 PM UTC
python manage.py setup_auto_indexing --time 15:30

# Update all schedules to run at 1 AM UTC
python manage.py setup_auto_indexing --time 01:00 --force
```

### Management Commands

#### `list_scheduled_tasks`
View and manage scheduled tasks.

```bash
# List all scheduled tasks
python manage.py list_scheduled_tasks

# List tasks for specific application
python manage.py list_scheduled_tasks --application-id 1

# Delete all scheduled tasks
python manage.py list_scheduled_tasks --delete

# Delete tasks for specific application
python manage.py list_scheduled_tasks --delete --application-id 1
```

**Options:**
- `--delete`: Remove scheduled tasks
- `--application-id ID`: Filter by application ID

#### `setup_complete_indexing`
Set up comprehensive indexing for all repositories.

```bash
# Set up complete indexing
python manage.py setup_complete_indexing

# Custom configuration
python manage.py setup_complete_indexing --workers 4 --timeout 3600
```

#### `start_intelligent_indexing`
Start intelligent indexing with AI-powered commit classification.

```bash
# Start intelligent indexing
python manage.py start_intelligent_indexing

# Custom model
python manage.py start_intelligent_indexing --model llama3.2:3b
```

## 🛠️ System Commands

### Django-Q Commands

#### `qcluster`
Start the Django-Q cluster (required for scheduled tasks).

```bash
python manage.py qcluster
```

#### `qmonitor`
Monitor Django-Q cluster status.

```bash
python manage.py qmonitor
```

#### `qinfo`
View task history and statistics.

```bash
python manage.py qinfo
```

### Database Commands

#### `makemigrations`
Create database migrations.

```bash
python manage.py makemigrations
```

#### `migrate`
Apply database migrations.

```bash
python manage.py migrate
```

#### `dbshell`
Open database shell.

```bash
python manage.py dbshell
```

## 📊 Analytics Commands

### Indexing Commands

#### `index_commits`
Index commits from repositories.

```bash
# Index all commits
python manage.py index_commits

# Index specific repository
python manage.py index_commits --repository-id 1

# Index with custom date range
python manage.py index_commits --start-date 2024-01-01 --end-date 2024-12-31
```

#### `index_repositories`
Index repository information.

```bash
# Index all repositories
python manage.py index_repositories

# Index specific repository
python manage.py index_repositories --repository-id 1
```

#### `index_pullrequests`
Index pull requests.

```bash
# Index all pull requests
python manage.py index_pullrequests

# Index specific repository
python manage.py index_pullrequests --repository-id 1
```

#### `index_releases`
Index releases.

```bash
# Index all releases
python manage.py index_releases

# Index specific repository
python manage.py index_releases --repository-id 1
```

#### `index_deployments`
Index deployments.

```bash
# Index all deployments
python manage.py index_deployments

# Index specific repository
python manage.py index_deployments --repository-id 1
```

### Classification Commands

#### `classify_existing_commits`
Classify existing commits using AI.

```bash
# Classify all commits
python manage.py classify_existing_commits

# Classify specific repository
python manage.py classify_existing_commits --repository-id 1

# Use custom model
python manage.py classify_existing_commits --model llama3.2:3b
```

## 🔧 Configuration Commands

### GitHub Commands

#### `check_github_permissions`
Check GitHub API permissions and rate limits.

```bash
# Check all permissions
python manage.py check_github_permissions

# Check specific user
python manage.py check_github_permissions --user-id 1
```

#### `check_rate_limit`
Check GitHub API rate limit status.

```bash
# Check rate limits
python manage.py check_rate_limit

# Check specific token
python manage.py check_rate_limit --token your-token
```

#### `setup_repository_indexing`
Set up repository indexing configuration.

```bash
# Set up indexing
python manage.py setup_repository_indexing

# Custom configuration
python manage.py setup_repository_indexing --workers 4 --timeout 3600
```

### Database Commands

#### `cleanup_duplicates`
Clean up duplicate records.

```bash
# Clean up all duplicates
python manage.py cleanup_duplicates

# Clean up specific table
python manage.py cleanup_duplicates --table commits
```

#### `merge_duplicate_developers`
Merge duplicate developer records.

```bash
# Merge all duplicates
python manage.py merge_duplicate_developers

# Merge specific developer
python manage.py merge_duplicate_developers --developer-id 1
```

## 🔍 Debug Commands

### Task Commands

#### `debug_task_creation`
Debug task creation issues.

```bash
# Debug task creation
python manage.py debug_task_creation

# Debug specific task
python manage.py debug_task_creation --task-id 1
```

#### `debug_task_storage`
Debug task storage issues.

```bash
# Debug task storage
python manage.py debug_task_storage
```

#### `verify_task_execution`
Verify task execution.

```bash
# Verify task execution
python manage.py verify_task_execution

# Verify specific task
python manage.py verify_task_execution --task-id 1
```

### System Commands

#### `inspect_django_q`
Inspect Django-Q configuration and status.

```bash
# Inspect Django-Q
python manage.py inspect_django_q
```

#### `test_github_tokens`
Test GitHub token validity.

```bash
# Test all tokens
python manage.py test_github_tokens

# Test specific token
python manage.py test_github_tokens --token your-token
```

## 🧹 Maintenance Commands

### Cleanup Commands

#### `cleanup_duplicate_tasks`
Clean up duplicate scheduled tasks.

```bash
# Clean up duplicate tasks
python manage.py cleanup_duplicate_tasks
```

#### `manage_orphan_aliases`
Manage orphaned developer aliases.

```bash
# Manage orphan aliases
python manage.py manage_orphan_aliases

# Clean up orphans
python manage.py manage_orphan_aliases --cleanup
```

#### `reset_developer_groups`
Reset developer groups.

```bash
# Reset all groups
python manage.py reset_developer_groups

# Reset specific group
python manage.py reset_developer_groups --group-id 1
```

### Verification Commands

#### `verify_deduplication`
Verify deduplication process.

```bash
# Verify deduplication
python manage.py verify_deduplication
```

#### `check_orphan_aliases`
Check for orphaned aliases.

```bash
# Check orphan aliases
python manage.py check_orphan_aliases
```

## 📈 Monitoring Commands

### Performance Commands

#### `compare_indexing_methods`
Compare different indexing methods.

```bash
# Compare methods
python manage.py compare_indexing_methods

# Custom comparison
python manage.py compare_indexing_methods --method1 git_local --method2 github_api
```

#### `test_corrected_indexing`
Test corrected indexing process.

```bash
# Test corrected indexing
python manage.py test_corrected_indexing
```

### Analysis Commands

#### `generate_sbom`
Generate Software Bill of Materials.

```bash
# Generate SBOM
python manage.py generate_sbom

# Custom output
python manage.py generate_sbom --output sbom.json
```

## 🚀 Utility Commands

### Development Commands

#### `restart_worker`
Restart background workers.

```bash
# Restart all workers
python manage.py restart_worker

# Restart specific worker
python manage.py restart_worker --worker-id 1
```

#### `schedule_daily_indexing`
Schedule daily indexing tasks.

```bash
# Schedule daily indexing
python manage.py schedule_daily_indexing

# Custom schedule
python manage.py schedule_daily_indexing --time 02:00
```

## 📚 Command Categories

### Indexing Commands
- `setup_auto_indexing` - Set up automatic indexing
- `index_commits` - Index repository commits
- `index_repositories` - Index repository information
- `index_pullrequests` - Index pull requests
- `index_releases` - Index releases
- `index_deployments` - Index deployments

### System Commands
- `qcluster` - Start Django-Q cluster
- `qmonitor` - Monitor cluster status
- `qinfo` - View task statistics
- `makemigrations` - Create migrations
- `migrate` - Apply migrations

### Debug Commands
- `debug_task_creation` - Debug task creation
- `debug_task_storage` - Debug task storage
- `verify_task_execution` - Verify task execution
- `inspect_django_q` - Inspect Django-Q
- `test_github_tokens` - Test GitHub tokens

### Maintenance Commands
- `cleanup_duplicates` - Clean up duplicates
- `merge_duplicate_developers` - Merge developers
- `manage_orphan_aliases` - Manage aliases
- `reset_developer_groups` - Reset groups
- `verify_deduplication` - Verify deduplication

## 📚 Related Documentation

- **[Technical Architecture](architecture.md)** - System architecture overview
- **[API Reference](api.md)** - API documentation
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions
- **[Docker Deployment](../deployment/docker.md)** - Docker deployment guide 