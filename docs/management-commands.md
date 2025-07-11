# Management Commands Reference

This document provides a quick reference for all management commands available in GitPulse, with a focus on automatic indexing features.

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

#### `collectstatic`
Collect static files for production.

```bash
python manage.py collectstatic
```

## 📊 Monitoring Commands

### Check System Status

```bash
# Check if Django-Q is running
ps aux | grep qcluster

# Check scheduled tasks
python manage.py list_scheduled_tasks

# Monitor cluster
python manage.py qmonitor
```

### Debug Commands

```bash
# View task history
python manage.py qinfo

# Check Django-Q status
python manage.py qmonitor

# Clear all schedules and start fresh
python manage.py list_scheduled_tasks --delete
python manage.py setup_auto_indexing --time 02:00
```

## 🚀 Quick Setup Workflow

### 1. Initial Setup

```bash
# Start Django-Q cluster
python manage.py qcluster

# Set up automatic indexing
python manage.py setup_auto_indexing --time 02:00

# Verify setup
python manage.py list_scheduled_tasks
```

### 2. Adding New Applications

```bash
# After creating new application and adding repositories
python manage.py setup_auto_indexing --time 02:00 --force
```

### 3. Troubleshooting

```bash
# Check if tasks are scheduled
python manage.py list_scheduled_tasks

# Restart Django-Q if needed
# Stop current qcluster process
python manage.py qcluster

# Clear and recreate schedules
python manage.py list_scheduled_tasks --delete
python manage.py setup_auto_indexing --time 02:00
```

## 📋 Command Summary

| Command | Purpose | Common Usage |
|---------|---------|--------------|
| `setup_auto_indexing` | Set up daily indexing | `--time 02:00` |
| `list_scheduled_tasks` | View/manage schedules | `--delete` |
| `qcluster` | Start task queue | Always running |
| `qmonitor` | Monitor cluster | Debug issues |
| `qinfo` | View task history | Debug issues |

## ⚠️ Important Notes

- **Django-Q must be running** for scheduled tasks to work
- **Time is in UTC** for all scheduling
- **Use `--force`** when updating existing schedules
- **Check logs** for task execution status
- **Monitor rate limits** in web interface

## 🔗 Related Documentation

- [Automatic Daily Indexing](./automatic-indexing.md)
- [Rate Limit Management](./rate-limit-management.md)
- [Django-Q Setup](./django-q-setup.md) 