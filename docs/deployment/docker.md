# Docker Deployment Guide

This guide covers Docker deployment for GitPulse, including setup, configuration, monitoring, and troubleshooting.

## 🐳 Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Git installed
- At least 4GB of RAM available
- 10GB of free disk space

### Step 1: Clone and Configure

```bash
git clone https://github.com/gitpulse/gitpulse.git
cd GitPulse
cp env.example .env
```

### Step 2: Start Services

```bash
docker-compose up -d --build
```

### Step 3: Initialize

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### Step 4: Access

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## 🏗️ Architecture

### Services Overview

GitPulse Docker setup includes the following services:

- **Web (Django)**: Main application server
- **PostgreSQL**: User and application data
- **MongoDB**: Analytics data storage
- **Redis**: Cache and task queue
- **Ollama**: AI for commit classification

### Service Details

#### Web Service (Django)
- **Port**: 8000
- **Image**: Custom Django application
- **Dependencies**: PostgreSQL, MongoDB, Redis
- **Volumes**: Static files, media files

#### PostgreSQL (User Data)
- **Port**: 5432
- **Database**: gitpulse
- **User**: gitpulse
- **Password**: gitpulse_password
- **Persistent Data**: User accounts, projects, repositories

#### MongoDB (Analytics)
- **Port**: 27017
- **Database**: gitpulse
- **Persistent Data**: Commits, pull requests, releases, deployments

#### Redis (Cache & Queue)
- **Port**: 6379
- **Purpose**: Django cache and task queue
- **Data**: Temporary cache and job queue

#### Ollama (AI)
- **Port**: 11434
- **Model**: llama3.2:3b (default)
- **Purpose**: Commit classification and analysis

## 📊 Database Schema

### PostgreSQL (Django)
- **Users**: User accounts and authentication
- **Projects**: Projects and their repositories
- **Repositories**: GitHub repositories
- **Developers**: Developer information

### MongoDB (Analytics)
- **Commits**: Commit data with classification
- **PullRequests**: Pull request data
- **Releases**: Release data
- **Deployments**: Deployment data
- **Developers**: Developer identity grouping

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

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

# GitHub OAuth
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

### Docker Compose Configuration

The `docker-compose.yml` file defines all services:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=True
    depends_on:
      - postgres
      - mongodb
      - redis
      - ollama
    volumes:
      - ./static:/app/static
      - ./media:/app/media

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: gitpulse
      POSTGRES_USER: gitpulse
      POSTGRES_PASSWORD: gitpulse_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  mongodb:
    image: mongo:6
    volumes:
      - mongodb_data:/data/db
    ports:
      - "27017:27017"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  postgres_data:
  mongodb_data:
  ollama_data:
```

## 📈 Monitoring and Logs

### Application Logs

```bash
# View application logs
docker-compose logs -f web

# View specific service logs
docker-compose logs -f postgres
docker-compose logs -f mongodb
docker-compose logs -f ollama
```

### Resource Monitoring

```bash
# Monitor resource usage
docker stats

# Check disk usage
docker system df

# View container status
docker-compose ps
```

### Health Checks

```bash
# Check if all services are running
docker-compose ps

# Test database connections
docker-compose exec web python manage.py dbshell
docker-compose exec web python manage.py shell
```

## 💾 Backup and Restore

### PostgreSQL Backup

```bash
# Create backup
docker-compose exec postgres pg_dump -U gitpulse gitpulse > backup_postgres.sql

# Restore backup
docker-compose exec -T postgres psql -U gitpulse gitpulse < backup_postgres.sql
```

### MongoDB Backup

```bash
# Create backup
docker-compose exec mongodb mongodump --db gitpulse --out /data/backup
docker cp gitpulse_mongodb_1:/data/backup ./backup_mongodb

# Restore backup
docker cp ./backup_mongodb gitpulse_mongodb_1:/data/backup
docker-compose exec mongodb mongorestore --db gitpulse /data/backup/gitpulse
```

### Volume Backup

```bash
# Backup all volumes
docker run --rm -v gitpulse_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz -C /data .
docker run --rm -v gitpulse_mongodb_data:/data -v $(pwd):/backup alpine tar czf /backup/mongodb_backup.tar.gz -C /data .
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Port Conflicts

```bash
# Check what's using the ports
lsof -i :8000
lsof -i :5432
lsof -i :27017

# Kill processes if needed
kill -9 <PID>
```

#### 2. Services Not Starting

```bash
# View detailed logs
docker-compose logs

# Restart all services
docker-compose down
docker-compose up -d
```

#### 3. Permission Issues

```bash
# Fix volume permissions
sudo chown -R $USER:$USER ./data
sudo chown -R $USER:$USER ./logs

# Fix Docker permissions
sudo usermod -aG docker $USER
```

#### 4. Ollama Not Responding

```bash
# Check if model is downloaded
docker-compose exec ollama ollama list

# Download model manually
docker-compose exec ollama ollama pull llama3.2:3b

# Check Ollama logs
docker-compose logs -f ollama
```

### Complete Cleanup

```bash
# Stop and remove all containers and volumes
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean unused Docker volumes
docker volume prune

# Clean unused Docker images
docker image prune -a
```

## ⚡ Performance Optimization

### Resource Requirements

- **RAM**: Minimum 4GB, recommended 8GB+
- **CPU**: Minimum 2 cores, recommended 4 cores+
- **Storage**: SSD recommended for databases
- **Network**: Stable internet connection for GitHub API

### Optimization Tips

1. **Database Optimization**
   ```bash
   # Increase PostgreSQL shared buffers
   POSTGRES_SHARED_BUFFERS=256MB
   ```

2. **Redis Optimization**
   ```bash
   # Configure Redis memory
   redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
   ```

3. **Ollama Optimization**
   ```bash
   # Use smaller model for faster inference
   OLLAMA_MODEL=llama3.2:1b
   ```

### Monitoring Commands

```bash
# Monitor resource usage
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Check disk usage
docker system df -v

# Monitor logs in real-time
docker-compose logs -f --tail=100
```

## 🔄 Updates and Maintenance

### Updating GitPulse

```bash
# Stop services
docker-compose down

# Pull latest changes
git pull

# Rebuild and restart
docker-compose up -d --build

# Apply migrations
docker-compose exec web python manage.py migrate

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Regular Maintenance

```bash
# Clean up unused containers
docker container prune

# Clean up unused images
docker image prune

# Clean up unused volumes
docker volume prune

# Clean up unused networks
docker network prune

# Full system cleanup
docker system prune -a
```

## 🔐 Security Considerations

### Production Security

1. **Use strong passwords**
   ```env
   POSTGRES_PASSWORD=very-long-random-password
   SECRET_KEY=very-long-random-secret-key
   ```

2. **Disable debug mode**
   ```env
   DEBUG=False
   ```

3. **Restrict network access**
   ```yaml
   # In docker-compose.yml
   networks:
     - internal
   ```

4. **Use secrets management**
   ```bash
   # Use Docker secrets
   echo "your-secret" | docker secret create db_password -
   ```

### Network Security

```yaml
# Example secure network configuration
networks:
  internal:
    driver: bridge
    internal: true
  external:
    driver: bridge
```

## 📚 Next Steps

- **[Production Deployment](production.md)** - Production deployment guide
- **[Configuration Guide](../getting-started/configuration.md)** - Advanced configuration
- **[Troubleshooting Guide](../technical/troubleshooting.md)** - Common issues and solutions
- **[GitHub Pages Deployment](github-pages.md)** - Deploy documentation to GitHub Pages 