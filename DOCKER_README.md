# GitPulse Docker Setup

This Docker setup provides a complete GitPulse environment with all necessary services running in containers.

## Services Included

- **Django Application**: The main GitPulse web application
- **MongoDB**: Database for storing application data
- **Redis**: Cache and task queue backend

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd GitPulse
   ```

2. **Start all services**:
   ```bash
   docker-compose up -d
   ```

3. **Access the application**:
   - Web application: http://localhost:8000
   - MongoDB: localhost:27017
   - Redis: localhost:6379

## First Time Setup

If this is your first time running GitPulse, you'll need to create a superuser:

```bash
docker-compose exec web python manage.py createsuperuser
```

## Data Persistence

The following data is persisted across container restarts:

- **MongoDB data**: Stored in Docker volume `mongodb_data`
- **Redis data**: Stored in Docker volume `redis_data`
- **SQLite database**: Mounted from `./db.sqlite3`
- **Application data**: Mounted from `./data/`
- **Logs**: Mounted from `./logs/`

## Management Commands

### View logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs web
docker-compose logs mongodb
docker-compose logs redis
```

### Run Django management commands
```bash
docker-compose exec web python manage.py <command>
```

### Access database shell
```bash
# MongoDB
docker-compose exec mongodb mongosh gitpulse

# Redis
docker-compose exec redis redis-cli
```

### Stop services
```bash
docker-compose down
```

### Stop and remove volumes (⚠️ This will delete all data)
```bash
docker-compose down -v
```

## Environment Variables

The following environment variables can be customized:

- `MONGODB_HOST`: MongoDB host (default: mongodb)
- `MONGODB_PORT`: MongoDB port (default: 27017)
- `MONGODB_NAME`: MongoDB database name (default: gitpulse)
- `REDIS_HOST`: Redis host (default: redis)
- `REDIS_PORT`: Redis port (default: 6379)

## Troubleshooting

### Services not starting
1. Check if ports are already in use:
   ```bash
   lsof -i :8000
   lsof -i :27017
   lsof -i :6379
   ```

2. Check container logs:
   ```bash
   docker-compose logs
   ```

### Database connection issues
1. Ensure MongoDB is running:
   ```bash
   docker-compose ps mongodb
   ```

2. Check MongoDB logs:
   ```bash
   docker-compose logs mongodb
   ```

### Redis connection issues
1. Ensure Redis is running:
   ```bash
   docker-compose ps redis
   ```

2. Check Redis logs:
   ```bash
   docker-compose logs redis
   ```

## Development

For development, you can mount the source code as a volume by modifying the `docker-compose.yml`:

```yaml
volumes:
  - .:/app
```

This will allow you to make changes to the code without rebuilding the container.

## Production Considerations

For production deployment, consider:

1. Using a production WSGI server (Gunicorn, uWSGI)
2. Setting up a reverse proxy (Nginx)
3. Using environment-specific settings
4. Implementing proper logging
5. Setting up monitoring and health checks
6. Using secrets management for sensitive data 