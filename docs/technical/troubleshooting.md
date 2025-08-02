# Troubleshooting Guide

This guide helps you resolve common issues with GitPulse installation, configuration, and operation.

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

### 4. Database Connection Issues

**Error**: `connection to database failed`

**Solutions**:
```bash
# Test PostgreSQL connection
python manage.py dbshell

# Test MongoDB connection
python manage.py shell
```
```python
from mongoengine import connect
# Should connect without errors
```

### 5. GitHub API Issues

**Error**: `GitHub API rate limit exceeded`

**Solutions**:
```bash
# Check rate limits
python manage.py check_rate_limit

# Check permissions
python manage.py check_github_permissions
```

### 6. Ollama Connection Issues

**Error**: `Ollama connection failed`

**Solutions**:
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check Docker container
docker-compose ps ollama

# Restart Ollama
docker-compose restart ollama
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

# Clean duplicate records
python manage.py cleanup_duplicates

# Merge duplicate developers
python manage.py merge_duplicate_developers
```

### Setup Commands

```bash
# Setup complete indexing system
python manage.py setup_complete_indexing --time 02:00 --spread

# Setup repository indexing only
python manage.py setup_repository_indexing --global-task --time 02:00

# Force recreate all schedules
python manage.py setup_complete_indexing --time 02:00 --spread --force

# Setup auto indexing
python manage.py setup_auto_indexing --time 02:00
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

# Test GitHub token
python manage.py test_github_tokens

# Test Django-Q
python manage.py inspect_django_q
```

## 🐳 Docker Issues

### Container Not Starting

```bash
# Check container logs
docker-compose logs web

# Check all services
docker-compose ps

# Restart all services
docker-compose down
docker-compose up -d
```

### Port Conflicts

```bash
# Check what's using the ports
lsof -i :8000
lsof -i :5432
lsof -i :27017

# Kill processes if needed
kill -9 <PID>
```

### Volume Issues

```bash
# Check volume permissions
ls -la ./data
ls -la ./logs

# Fix permissions
sudo chown -R $USER:$USER ./data
sudo chown -R $USER:$USER ./logs
```

## 🔍 Debug Commands

### Debug Task Issues

```bash
# Debug task creation
python manage.py debug_task_creation

# Debug task storage
python manage.py debug_task_storage

# Verify task execution
python manage.py verify_task_execution
```

### Debug Database Issues

```bash
# Check PostgreSQL
docker-compose exec postgres psql -U gitpulse -d gitpulse -c "\dt"

# Check MongoDB
docker-compose exec mongodb mongo gitpulse --eval "db.getCollectionNames()"

# Check Django models
python manage.py shell -c "from django.apps import apps; [print(f'{app.label}: {app.models_module}') for app in apps.get_app_configs()]"
```

### Debug GitHub Issues

```bash
# Test GitHub tokens
python manage.py test_github_tokens

# Check GitHub permissions
python manage.py check_github_permissions

# Check rate limits
python manage.py check_rate_limit
```

## 🚨 Emergency Procedures

### Complete Reset

```bash
# Stop all services
docker-compose down

# Remove all data
docker-compose down -v
docker system prune -a

# Rebuild from scratch
docker-compose up -d --build

# Reinitialize
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### Database Recovery

```bash
# Backup before recovery
docker-compose exec postgres pg_dump -U gitpulse gitpulse > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U gitpulse gitpulse < backup.sql
```

### Task Queue Recovery

```bash
# Clear all tasks
python manage.py shell -c "from django_q.models import Task; Task.objects.all().delete()"

# Clear all schedules
python manage.py shell -c "from django_q.models import Schedule; Schedule.objects.all().delete()"

# Restart cluster
python manage.py qcluster
```

## 📈 Performance Issues

### Slow Indexing

**Symptoms**: Indexing takes too long or fails

**Solutions**:
```bash
# Increase workers
python manage.py setup_complete_indexing --workers 8

# Increase timeout
python manage.py setup_complete_indexing --timeout 7200

# Use smaller Ollama model
export OLLAMA_MODEL=llama3.2:1b
```

### Memory Issues

**Symptoms**: Out of memory errors

**Solutions**:
```bash
# Check memory usage
docker stats

# Increase Docker memory limit
# Edit docker-compose.yml to add memory limits

# Optimize database
docker-compose exec postgres psql -U gitpulse -d gitpulse -c "VACUUM ANALYZE;"
```

### Network Issues

**Symptoms**: GitHub API timeouts

**Solutions**:
```bash
# Check network connectivity
curl -I https://api.github.com

# Increase timeout
export GITHUB_API_TIMEOUT=60

# Use proxy if needed
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
```

## 🔐 Security Issues

### Token Security

**Symptoms**: GitHub token errors

**Solutions**:
```bash
# Check token validity
python manage.py test_github_tokens

# Regenerate token
# Go to GitHub Settings > Developer settings > Personal access tokens

# Update environment
# Edit .env file with new token
```

### Database Security

**Symptoms**: Database connection errors

**Solutions**:
```bash
# Check database permissions
docker-compose exec postgres psql -U gitpulse -d gitpulse -c "\du"

# Reset database password
docker-compose exec postgres psql -U postgres -c "ALTER USER gitpulse PASSWORD 'new_password';"
```

## 📚 Getting Help

### Log Files

```bash
# Application logs
docker-compose logs -f web

# Database logs
docker-compose logs -f postgres
docker-compose logs -f mongodb

# Ollama logs
docker-compose logs -f ollama
```

### Debug Information

```bash
# Collect debug info
python manage.py shell -c "
from django.conf import settings
print(f'DEBUG: {settings.DEBUG}')
print(f'DATABASES: {settings.DATABASES}')
print(f'CACHES: {settings.CACHES}')
"
```

### Community Support

- **GitHub Issues**: [Create an issue](https://github.com/gitpulse/gitpulse/issues)
- **Documentation**: Check the [Configuration Guide](../getting-started/configuration.md)
- **Management Commands**: See [Management Commands Reference](management-commands.md)

## 📚 Related Documentation

- **[Management Commands](management-commands.md)** - Available management commands
- **[Configuration Guide](../getting-started/configuration.md)** - Environment configuration
- **[Docker Deployment](../deployment/docker.md)** - Docker deployment guide
- **[GitHub Setup](../user-guide/github-setup.md)** - GitHub integration setup 