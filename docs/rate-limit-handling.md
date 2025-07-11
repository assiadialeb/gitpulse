# GitHub Rate Limit Handling

This document explains how the GitPulse application handles GitHub API rate limits and automatically restarts interrupted indexing processes.

## Overview

When the GitHub API rate limit is exceeded during indexing or synchronization, the system:

1. **Catches the rate limit error** and stops the current process gracefully
2. **Schedules automatic restart** when the rate limit resets
3. **Provides user feedback** about the rate limit status and restart timing
4. **Monitors and processes** pending restarts automatically

## How It Works

### 1. Rate Limit Detection

The system detects rate limits in several ways:

- **GitHub API Headers**: Monitors `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers
- **Error Messages**: Parses rate limit error messages to extract reset times
- **HTTP Status Codes**: Detects 403 errors with rate limit information

### 2. Automatic Restart Scheduling

When a rate limit is hit:

1. **Parse Reset Time**: Extract the reset time from GitHub's response
2. **Create Reset Record**: Store rate limit information in MongoDB
3. **Schedule Restart**: Use Django-Q to schedule automatic restart
4. **User Notification**: Show rate limit status in the UI

### 3. Restart Processing

The system includes background tasks that:

- **Monitor Pending Restarts**: Check every 5 minutes for tasks ready to restart
- **Execute Restarts**: Automatically restart tasks when rate limits reset
- **Clean Up**: Remove old rate limit records after 7 days

## Usage

### For Users

1. **Start Indexing**: Begin indexing as normal
2. **Rate Limit Hit**: If rate limit is exceeded, you'll see a notification
3. **Automatic Restart**: The system will automatically restart when the rate limit resets
4. **Monitor Status**: Check the rate limit status panel in the UI

### For Developers

#### Setting Up Rate Limit Monitoring

```bash
# Set up the monitoring tasks
python manage.py setup_rate_limit_monitoring
```

#### Manual Rate Limit Handling

```python
from analytics.services import RateLimitService
from analytics.github_service import GitHubRateLimitError

# Handle a rate limit error
result = RateLimitService.handle_rate_limit_error(
    user_id=user.id,
    github_username='username',
    error=GitHubRateLimitError("Rate limit exceeded"),
    task_type='indexing',
    task_data={'application_id': 1, 'user_id': user.id}
)
```

#### Checking Rate Limit Status

```python
from analytics.models import RateLimitReset

# Get pending resets for a user
pending_resets = RateLimitReset.objects.filter(
    user_id=user.id,
    status__in=['pending', 'scheduled']
)
```

## Configuration

### Rate Limit Thresholds

The system warns when rate limit is low and stops when it's exhausted:

- **Warning Threshold**: 10 requests remaining
- **Stop Threshold**: 0 requests remaining
- **Buffer Time**: 1 minute after reset time

### Monitoring Intervals

- **Restart Check**: Every 5 minutes
- **Cleanup**: Daily at 2 AM
- **UI Update**: Every 30 seconds

## API Endpoints

### Get Rate Limit Status

```
GET /analytics/api/rate-limit-status/
```

Response:
```json
{
  "success": true,
  "github_username": "username",
  "pending_resets": [
    {
      "id": "reset_id",
      "task_type": "indexing",
      "reset_time": "2025-01-11T23:14:51Z",
      "time_until_reset": 3600,
      "status": "pending"
    }
  ],
  "total_pending": 1
}
```

### Cancel Rate Limit Restart

```
POST /analytics/api/rate-limit-restart/{reset_id}/cancel/
```

## Database Schema

### RateLimitReset Collection

```javascript
{
  user_id: Number,
  github_username: String,
  rate_limit_reset_time: DateTime,
  rate_limit_remaining: Number,
  rate_limit_limit: Number,
  pending_task_type: String, // 'indexing', 'sync', 'background'
  pending_task_data: Object,
  original_task_id: String,
  status: String, // 'pending', 'scheduled', 'completed', 'failed', 'cancelled'
  created_at: DateTime,
  scheduled_at: DateTime,
  completed_at: DateTime,
  error_message: String,
  retry_count: Number,
  max_retries: Number
}
```

## Troubleshooting

### Common Issues

1. **Restart Not Scheduled**: Check Django-Q worker is running
2. **Wrong Reset Time**: Verify GitHub API response parsing
3. **UI Not Updating**: Check browser console for JavaScript errors

### Debug Commands

```bash
# Check pending rate limit resets
python manage.py shell
>>> from analytics.models import RateLimitReset
>>> RateLimitReset.objects.filter(status='pending').count()

# Check Django-Q schedules
>>> from django_q.models import Schedule
>>> Schedule.objects.filter(func__contains='rate_limit').count()
```

### Logs

Rate limit events are logged with these patterns:

- `Rate limit hit for user {username}. Restart scheduled for {time}`
- `Scheduled restart for {task_type} task at {time}`
- `Successfully restarted {task_type} task with ID {task_id}`

## Best Practices

1. **Monitor Rate Limits**: Check the UI regularly for pending restarts
2. **Plan Large Indexing**: Schedule heavy indexing during off-peak hours
3. **Use Multiple Tokens**: Consider using GitHub Apps for higher rate limits
4. **Monitor Logs**: Check application logs for rate limit events

## Future Improvements

- **Multiple Token Support**: Rotate between multiple GitHub tokens
- **Rate Limit Prediction**: Predict when rate limits will be hit
- **Smart Scheduling**: Optimize task scheduling to avoid rate limits
- **Webhook Integration**: Use GitHub webhooks to reduce API calls 