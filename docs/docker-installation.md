# GitPulse Installation with Docker

This guide explains how to install and configure GitPulse using Docker with PostgreSQL, MongoDB, Redis, and Ollama.

## Prerequisites

- Docker and Docker Compose installed
- Git installed
- At least 4GB of RAM available
- 10GB of free disk space

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/gitpulse.git
cd gitpulse
```

### 2. Environment configuration

Create a `.env` file at the project root:

```bash
cp env.example .env
```

Modify the `.env` file according to your needs:

```env
# Django Settings
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Settings
POSTGRES_DB=gitpulse
POSTGRES_USER=gitpulse
POSTGRES_PASSWORD=gitpulse_password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# MongoDB Settings
MONGODB_HOST=mongodb
MONGODB_PORT=27017
MONGODB_NAME=gitpulse

# Redis Settings
REDIS_HOST=redis
REDIS_PORT=6379

# Ollama Settings
OLLAMA_HOST=ollama
OLLAMA_PORT=11434

# GitHub OAuth (optional for development)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

### 3. Start the services

```bash
# Build and start all services
docker-compose up -d --build
```

This command will:
- Build the Docker image of the application
- Start PostgreSQL (Django database)
- Start MongoDB (analytics database)
- Start Redis (cache)
- Start Ollama (AI for commit classification)
- Start the Django application

### 4. Verify that all services are started

```bash
docker-compose ps
```

You should see all services with "Up" status.

### 5. Initialize the database

```bash
# Create Django migrations
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Create a superuser
docker-compose exec web python manage.py createsuperuser
```

### 6. Collect static files

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

## Access to the application

- **Web application**: http://localhost:8000
- **Django Admin**: http://localhost:8000/admin
- **PostgreSQL**: localhost:5432
- **MongoDB**: localhost:27017
- **Redis**: localhost:6379
- **Ollama**: http://localhost:11434

## GitHub OAuth Configuration (optional)

To use GitHub authentication:

1. Create an OAuth application on GitHub:
   - Go to https://github.com/settings/developers
   - Click "New OAuth App"
   - Fill in the information:
     - Application name: GitPulse
     - Homepage URL: http://localhost:8000
     - Authorization callback URL: http://localhost:8000/accounts/github/login/callback/

2. Add the credentials to your `.env`:
   ```env
   GITHUB_CLIENT_ID=your-client-id
   GITHUB_CLIENT_SECRET=your-client-secret
   ```

3. Restart the services:
   ```bash
   docker-compose restart web
   ```

## Useful Commands

### Service Management

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# View logs for a specific service
docker-compose logs -f web

# Restart a service
docker-compose restart web
```

### Database

```bash
# Access PostgreSQL shell
docker-compose exec postgres psql -U gitpulse -d gitpulse

# Access MongoDB shell
docker-compose exec mongodb mongosh

# Access Redis shell
docker-compose exec redis redis-cli
```

### Django Application

```bash
# Access Django shell
docker-compose exec web python manage.py shell

# Create a superuser
docker-compose exec web python manage.py createsuperuser

# View running tasks
docker-compose exec web python manage.py shell
# >>> from django_q.models import Schedule
# >>> Schedule.objects.all()
```

### Ollama

```bash
# View available models
docker-compose exec ollama ollama list

# Test Ollama
curl http://localhost:11434/api/generate -d '{
  "model": "gemma3:1b",
  "prompt": "Hello, how are you?"
}'
```

## Data Structure

### PostgreSQL (Django)
- **Users**: Users and authentication
- **Projects**: Projects and their repositories
- **Repositories**: GitHub repositories
- **Developers**: Developer information

### MongoDB (Analytics)
- **Commits**: Commit data with classification
- **PullRequests**: Pull request data
- **Releases**: Release data
- **Deployments**: Deployment data
- **Developers**: Developer identity grouping

## Monitoring and Logs

### Application Logs
```bash
docker-compose logs -f web
```

### Database Logs
```bash
docker-compose logs -f postgres
docker-compose logs -f mongodb
```

### Ollama Logs
```bash
docker-compose logs -f ollama
```

## Backup and Restoration

### PostgreSQL Backup
```bash
docker-compose exec postgres pg_dump -U gitpulse gitpulse > backup_postgres.sql
```

### MongoDB Backup
```bash
docker-compose exec mongodb mongodump --db gitpulse --out /data/backup
docker cp gitpulse_mongodb_1:/data/backup ./backup_mongodb
```

### PostgreSQL Restoration
```bash
docker-compose exec -T postgres psql -U gitpulse gitpulse < backup_postgres.sql
```

### MongoDB Restoration
```bash
docker cp ./backup_mongodb gitpulse_mongodb_1:/data/backup
docker-compose exec mongodb mongorestore --db gitpulse /data/backup/gitpulse
```

## Troubleshooting

### Common Issues

1. **Ports already in use**
   ```bash
   # Check used ports
   lsof -i :8000
   lsof -i :5432
   lsof -i :27017
   ```

2. **Services not starting**
   ```bash
   # View detailed logs
   docker-compose logs
   
   # Restart all services
   docker-compose down
   docker-compose up -d
   ```

3. **Permission issues**
   ```bash
   # Give proper permissions to volumes
   sudo chown -R $USER:$USER ./data
   sudo chown -R $USER:$USER ./logs
   ```

4. **Ollama not responding**
   ```bash
   # Check if the model is downloaded
   docker-compose exec ollama ollama list
   
   # Download the model manually
   docker-compose exec ollama ollama pull gemma3:1b
   ```

### Complete Cleanup

```bash
# Stop and remove all containers and volumes
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean unused Docker volumes
docker volume prune
```

## Performance

### Recommended Optimizations

1. **Memory**: Allocate at least 4GB of RAM
2. **CPU**: At least 2 cores for good performance
3. **Disk**: SSD recommended for databases

### Resource Monitoring

```bash
# View resource usage
docker stats

# View disk space used
docker system df
```

## Support

For help:
- Check logs: `docker-compose logs`
- Review documentation: `/docs`
- Open an issue on GitHub

## Updates

To update GitPulse:

```bash
# Stop services
docker-compose down

# Get latest changes
git pull

# Rebuild and restart
docker-compose up -d --build

# Apply migrations
docker-compose exec web python manage.py migrate
``` 