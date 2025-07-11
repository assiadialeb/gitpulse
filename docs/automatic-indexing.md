# Automatic Daily Indexing

GitPulse includes a powerful automatic indexing system that keeps your repository data up-to-date without manual intervention. This feature uses Django-Q's built-in scheduler to run indexing tasks automatically on a daily basis.

## 🚀 Overview

The automatic indexing system:
- **Runs daily** at a configurable time (default: 2 AM UTC)
- **Handles rate limits** automatically using the built-in rate limit management
- **Scales automatically** for any number of applications
- **Requires no additional tools** - uses existing Django-Q infrastructure

## 📋 Prerequisites

Before setting up automatic indexing, ensure:

1. **Django-Q is running**: The cluster must be active
   ```bash
   python manage.py qcluster
   ```

2. **Applications are configured**: Applications must have repositories added and initial indexing completed

3. **GitHub tokens are valid**: User GitHub tokens must be active and have proper permissions

## 🛠️ Setup Instructions

### 1. Set Up Automatic Indexing for All Applications

```bash
# Set up daily indexing at 2 AM UTC (default)
python manage.py setup_auto_indexing

# Set up daily indexing at a custom time
python manage.py setup_auto_indexing --time 03:00

# Force recreate all schedules (if you need to update existing ones)
python manage.py setup_auto_indexing --time 02:00 --force
```

### 2. For New Applications

After creating a new application and adding repositories, run:

```bash
python manage.py setup_auto_indexing --time 02:00 --force
```

This will create schedules for all applications, including the new one.

## 📊 Management Commands

### View Scheduled Tasks

```bash
# List all scheduled tasks
python manage.py list_scheduled_tasks

# List tasks for a specific application
python manage.py list_scheduled_tasks --application-id 1
```

### Remove Scheduled Tasks

```bash
# Remove all scheduled indexing tasks
python manage.py list_scheduled_tasks --delete

# Remove tasks for a specific application
python manage.py list_scheduled_tasks --delete --application-id 1
```

## ⚙️ Configuration Options

### Time Format

Use 24-hour format (HH:MM) for scheduling:

```bash
# Examples
python manage.py setup_auto_indexing --time 02:00  # 2 AM UTC
python manage.py setup_auto_indexing --time 14:30  # 2:30 PM UTC
python manage.py setup_auto_indexing --time 00:00  # Midnight UTC
```

### Schedule Types

The system creates **daily schedules** that:
- Run once per day at the specified time
- Repeat indefinitely until manually removed
- Automatically handle timezone conversions

## 🔄 How It Works

### 1. Task Scheduling

When you run `setup_auto_indexing`:

1. **Scans all applications** in the database
2. **Creates Django-Q schedules** for each application
3. **Sets next run time** to the specified time (tomorrow if time has passed today)
4. **Configures daily repetition** with infinite repeats

### 2. Task Execution

Each day at the scheduled time:

1. **Django-Q scheduler** triggers the background indexing task
2. **Runs `background_indexing_task`** for each application
3. **Syncs all repositories** in the application
4. **Handles rate limits** automatically if GitHub API limits are hit
5. **Logs results** for monitoring

### 3. Rate Limit Handling

The system automatically handles GitHub API rate limits:

- **Detects rate limit errors** during indexing
- **Schedules automatic restarts** when limits reset
- **Uses existing rate limit infrastructure** (no additional setup needed)
- **Logs rate limit events** for monitoring

## 📈 Monitoring

### Check Task Status

```bash
# View all scheduled tasks
python manage.py list_scheduled_tasks

# Check Django-Q cluster status
# Look for scheduled tasks in the qcluster output
```

### Logs to Monitor

1. **Django-Q cluster logs**: Shows task execution and scheduling
2. **Application logs**: Shows indexing progress and errors
3. **Rate limit logs**: Shows when rate limits are hit and restarts scheduled

### Web Interface

The web interface shows:
- **Rate limit status** in the top-right corner
- **Indexing progress** when manually triggered
- **Application statistics** that update after each indexing run

## 🔧 Troubleshooting

### Common Issues

#### 1. Tasks Not Running

**Symptoms**: No indexing happens at scheduled times

**Solutions**:
```bash
# Check if Django-Q is running
ps aux | grep qcluster

# Restart Django-Q cluster
python manage.py qcluster

# Check scheduled tasks
python manage.py list_scheduled_tasks
```

#### 2. Rate Limit Errors

**Symptoms**: Tasks fail with rate limit errors

**Solutions**:
- The system automatically handles this
- Check rate limit status in the web interface
- Monitor logs for restart scheduling

#### 3. Invalid GitHub Tokens

**Symptoms**: Tasks fail with authentication errors

**Solutions**:
- Check GitHub token validity in user settings
- Ensure tokens have proper repository permissions
- Re-authenticate if needed

### Debug Commands

```bash
# Check Django-Q status
python manage.py qmonitor

# View task history
python manage.py qinfo

# Clear all schedules (start fresh)
python manage.py list_scheduled_tasks --delete
python manage.py setup_auto_indexing --time 02:00
```

## 🎯 Best Practices

### 1. Scheduling Times

- **Choose off-peak hours**: 2-4 AM UTC is usually good
- **Consider timezone**: Schedule when your team is not actively working
- **Spread load**: If you have many applications, consider different times

### 2. Monitoring

- **Regular checks**: Monitor logs weekly
- **Rate limit awareness**: Check rate limit status regularly
- **Performance monitoring**: Watch for indexing duration increases

### 3. Maintenance

- **Review schedules**: Periodically check scheduled tasks
- **Update tokens**: Ensure GitHub tokens remain valid
- **Clean up**: Remove schedules for deleted applications

## 🔄 Integration with Manual Indexing

The automatic system works alongside manual indexing:

- **Manual indexing**: Still available via web interface
- **No conflicts**: Automatic and manual indexing can run simultaneously
- **Same infrastructure**: Both use the same background task system
- **Same rate limit handling**: Both benefit from rate limit management

## 📝 Example Workflow

### Setting Up a New Application

1. **Create application** via web interface
2. **Add repositories** to the application
3. **Run initial indexing** manually (first time)
4. **Set up automatic indexing**:
   ```bash
   python manage.py setup_auto_indexing --time 02:00 --force
   ```
5. **Verify setup**:
   ```bash
   python manage.py list_scheduled_tasks
   ```

### Daily Operations

1. **Monitor logs** for successful indexing
2. **Check rate limit status** in web interface
3. **Review application statistics** for updates
4. **No manual intervention needed** - everything runs automatically

## 🚨 Important Notes

- **Django-Q must be running**: The cluster is essential for scheduled tasks
- **Time is in UTC**: All scheduling uses UTC timezone
- **Rate limits are handled**: No need to worry about GitHub API limits
- **Infinite repetition**: Tasks repeat daily until manually removed
- **No additional tools**: Uses existing Django-Q infrastructure

## 📚 Related Documentation

- [Rate Limit Management](./rate-limit-management.md)
- [Background Tasks](./background-tasks.md)
- [GitHub Integration](./github-integration.md)
- [Django-Q Configuration](./django-q-setup.md) 