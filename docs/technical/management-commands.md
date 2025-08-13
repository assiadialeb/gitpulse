# Management Commands Reference

This document provides a complete reference for all management commands available in GitPulse.

## 🔄 Automatic Indexing Commands

### Indexing Setup

#### `setup_auto_indexing`
Set up automatic daily indexing for all applications (deprecated - use `setup_repository_indexing`).

```bash
# Basic setup (02:00 UTC default)
python manage.py setup_auto_indexing

# Custom time
python manage.py setup_auto_indexing --time 03:00

# Force recreate all schedules
python manage.py setup_auto_indexing --time 02:00 --force
```

**Options:**
- `--time HH:MM` : Set custom time (24-hour format)
- `--force` : Recreate existing schedules

#### `setup_repository_indexing`
Set up automatic daily indexing for repositories (recommended).

```bash
# Global task (recommended)
python manage.py setup_repository_indexing --global-task --time 02:00

# Individual tasks per repository
python manage.py setup_repository_indexing --time 02:00

# Force recreate
python manage.py setup_repository_indexing --time 02:00 --force
```

**Options:**
- `--time HH:MM` : Execution time (default: 02:00)
- `--force` : Recreate existing schedules
- `--global-task` : Create a single global task instead of individual tasks

#### `setup_complete_indexing`
Set up a complete indexing system with all tasks.

```bash
# Complete setup
python manage.py setup_complete_indexing

# Setup with task spreading
python manage.py setup_complete_indexing --spread

# Custom time
python manage.py setup_complete_indexing --time 02:00 --force
```

**Options:**
- `--time HH:MM` : Base time for tasks
- `--force` : Recreate all schedules
- `--spread` : Spread tasks across different hours

#### `setup_rate_limit_monitoring`
Set up automatic GitHub rate limit monitoring.

```bash
python manage.py setup_rate_limit_monitoring
```

**Features:**
- Process pending restarts every 5 minutes
- Clean up old rate limit resets (daily)

## 🚀 Manual Indexing Commands

### Intelligent Indexing

#### `start_intelligent_indexing`
Start intelligent indexing for repositories.

```bash
# Complete indexing for all repositories
python manage.py start_intelligent_indexing

# Specific repository
python manage.py start_intelligent_indexing --repository-id 123

# Specific entity types
python manage.py start_intelligent_indexing --entity-types commits pullrequests

# Dry-run mode
python manage.py start_intelligent_indexing --dry-run
```

**Options:**
- `--repository-id ID` : Specific repository
- `--entity-types` : Entity types (commits, pullrequests, releases, deployments)
- `--dry-run` : Simulation without starting tasks

### Entity-Specific Indexing

#### `index_commits`
Index GitHub commits with PR links.

```bash
# All repositories
python manage.py index_commits --all

# Specific repository
python manage.py index_commits --repo-id 123

# Synchronous mode
python manage.py index_commits --repo-id 123 --sync

# Reset indexing state
python manage.py index_commits --repo-id 123 --reset

# Show status
python manage.py index_commits --status
```

**Options:**
- `--repo-id ID` : Specific repository
- `--all` : All indexed repositories
- `--batch-size N` : Batch size in days (default: 7)
- `--sync` : Synchronous execution
- `--reset` : Reset indexing state
- `--status` : Show indexing status

#### `index_pullrequests`
Index GitHub pull requests.

```bash
# All repositories
python manage.py index_pullrequests --all

# Specific repository
python manage.py index_pullrequests --repo-id 123

# Synchronous mode
python manage.py index_pullrequests --repo-id 123 --sync
```

#### `index_releases`
Index GitHub releases.

```bash
# All repositories
python manage.py index_releases --all

# Specific repository
python manage.py index_releases --repo-id 123

# Synchronous mode
python manage.py index_releases --repo-id 123 --sync
```

#### `index_deployments`
Index GitHub deployments.

```bash
# All repositories
python manage.py index_deployments --all

# Specific repository
python manage.py index_deployments --repo-id 123

# Synchronous mode
python manage.py index_deployments --repo-id 123 --sync
```

#### `index_repositories`
Index repository metadata.

```bash
# All repositories
python manage.py index_repositories --all

# Specific repository
python manage.py index_repositories --repo-id 123

# Synchronous mode
python manage.py index_repositories --repo-id 123 --sync
```

### Specialized Indexing

#### `index_codeql_repository`
Index CodeQL vulnerabilities for repositories.

```bash
# Specific repository
python manage.py index_codeql_repository --repo-id 123

# All repositories
python manage.py index_codeql_repository --all

# Synchronous mode
python manage.py index_codeql_repository --repo-id 123 --sync
```

## 🔄 Backfill Commands

#### `backfill_commits_git_local`
Complete commit backfill using Git local (no rate limits).

```bash
# All repositories
python manage.py backfill_commits_git_local

# Specific repository
python manage.py backfill_commits_git_local --repository-id 123

# Dry-run mode
python manage.py backfill_commits_git_local --dry-run
```

**Advantages:**
- No GitHub rate limits
- No pagination
- Complete history

#### `backfill_sonarcloud`
Backfill SonarCloud metrics.

```bash
# All repositories
python manage.py backfill_sonarcloud

# Specific repository
python manage.py backfill_sonarcloud --repo-id 123

# Dry-run mode
python manage.py backfill_sonarcloud --dry-run
```

## 🧠 Intelligent Analysis Commands

#### `classify_existing_commits`
Reclassify commits marked as "other" using Ollama LLM.

```bash
# Complete reclassification
python manage.py classify_existing_commits

# Dry-run mode
python manage.py classify_existing_commits --dry-run

# Limit for testing
python manage.py classify_existing_commits --limit 50

# Custom batch size
python manage.py classify_existing_commits --batch-size 200
```

**Options:**
- `--dry-run` : Simulation without changes
- `--batch-size N` : Batch size (default: 100)
- `--limit N` : Limit for testing

#### `calculate_shs_all_repos`
Calculate Security Health Score (SHS) for repositories.

```bash
# All repositories
python manage.py calculate_shs_all_repos

# Specific repository
python manage.py calculate_shs_all_repos --repository-id 123

# Force recalculation
python manage.py calculate_shs_all_repos --force
```

**Options:**
- `--repository-id ID` : Specific repository
- `--force` : Force recalculation even if SHS exists

#### `generate_sbom`
Generate SBOM (Software Bill of Materials) for repositories.

```bash
# All repositories
python manage.py generate_sbom --all

# Specific repository
python manage.py generate_sbom --repo-id 123

# Synchronous mode
python manage.py generate_sbom --repo-id 123 --sync

# Force generation
python manage.py generate_sbom --repo-id 123 --force
```

**Options:**
- `--repo-id ID` : Specific repository
- `--all` : All indexed repositories
- `--sync` : Synchronous execution
- `--force` : Force generation

## 🔧 Maintenance Commands

#### `reset_developer_groups`
Reset developer groups.

```bash
python manage.py reset_developer_groups
```

#### `compare_indexing_methods`
Compare indexing methods (empty file - to be implemented).

```bash
python manage.py compare_indexing_methods
```

## 🛠️ Django-Q Commands

#### `qcluster`
Start Django-Q cluster (required for scheduled tasks).

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

#### `qmemory`
View cluster memory usage.

```bash
python manage.py qmemory
```

## 📊 Base Django Commands

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

#### `check`
Check project configuration.

```bash
python manage.py check
```

#### `shell`
Open Django interactive shell.

```bash
python manage.py shell
```

## 🎯 Recommended Usage

### Initial Setup

1. **Set up automatic indexing:**
   ```bash
   python manage.py setup_repository_indexing --global-task --time 02:00
   ```

2. **Set up rate limit monitoring:**
   ```bash
   python manage.py setup_rate_limit_monitoring
   ```

3. **Start Django-Q cluster:**
   ```bash
   python manage.py qcluster
   ```

### Manual Indexing

1. **Complete repository indexing:**
   ```bash
   python manage.py start_intelligent_indexing --repository-id 123
   ```

2. **Git local backfill (no limits):**
   ```bash
   python manage.py backfill_commits_git_local --repository-id 123
   ```

3. **Commit reclassification:**
   ```bash
   python manage.py classify_existing_commits --dry-run
   ```

### Maintenance

1. **Calculate security scores:**
   ```bash
   python manage.py calculate_shs_all_repos
   ```

2. **Generate SBOMs:**
   ```bash
   python manage.py generate_sbom --all
   ```

## 📝 Important Notes

- **Django-Q required** : Cluster must be active for scheduled tasks
- **UTC times** : All scheduling uses UTC timezone
- **Rate limits** : Automatically handled by the system
- **Automatic indexing** : Works without manual intervention
- **Dry-run mode** : Always available for testing commands 