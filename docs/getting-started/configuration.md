# Configuration Guide

GitPulse uses `python-decouple` to manage configuration securely and flexibly. All settings can be configured via environment variables or a `.env` file.

## 🔧 Environment Variables

### Django Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `True` | Enable/disable debug mode |
| `SECRET_KEY` | `django-insecure-...` | Django secret key for security |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | Comma-separated list of allowed hosts |
| `LANGUAGE_CODE` | `en-us` | Language code |
| `TIME_ZONE` | `Europe/Paris` | Timezone |

### Database Configuration

#### MongoDB (Analytics Data)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_HOST` | `localhost` | MongoDB host |
| `MONGODB_PORT` | `27017` | MongoDB port |
| `MONGODB_NAME` | `gitpulse` | MongoDB database name |

#### PostgreSQL (User Data)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `gitpulse_new` | PostgreSQL database name |
| `POSTGRES_USER` | `gitpulse_user` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `gitpulse_password` | PostgreSQL password |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |

### GitPulse Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEXING_SERVICE` | `git_local` | Choose indexing service (`git_local` or `github_api`) |
| `GITHUB_API_RATE_LIMIT_WARNING` | `10` | Rate limit warning threshold |
| `GITHUB_API_TIMEOUT` | `30` | API timeout in seconds |

### Ollama Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model name |

### Django-Q Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `Q_WORKERS` | `4` | Number of worker processes |
| `Q_RECYCLE` | `500` | Worker recycle count |
| `Q_TIMEOUT` | `3600` | Task timeout in seconds |
| `Q_RETRY` | `4000` | Retry count |
| `Q_SAVE_LIMIT` | `250` | Save limit |
| `Q_QUEUE_LIMIT` | `500` | Queue limit |
| `Q_CPU_AFFINITY` | `1` | CPU affinity |

### Cache Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TIMEOUT` | `3600` | Cache timeout in seconds |
| `CACHE_MAX_ENTRIES` | `1000` | Maximum cache entries |
| `ANALYTICS_CACHE_TIMEOUT` | `3600` | Analytics cache timeout |
| `PR_METRICS_CACHE_TIMEOUT` | `1800` | PR metrics cache timeout |
| `COMMIT_METRICS_CACHE_TIMEOUT` | `7200` | Commit metrics cache timeout |

## 📝 Configuration Methods

### Method 1: .env File (Recommended)

1. **Copy the example file**
   ```bash
   cp env.example .env
   ```

2. **Edit the configuration**
   ```bash
   # Edit .env with your preferred editor
   nano .env
   # or
   vim .env
   ```

3. **Example .env file**
   ```env
   # Django Core
   DEBUG=True
   SECRET_KEY=your-secret-key-here
   ALLOWED_HOSTS=localhost,127.0.0.1,testserver
   LANGUAGE_CODE=en-us
   TIME_ZONE=Europe/Paris

   # Database Configuration
   MONGODB_HOST=localhost
   MONGODB_PORT=27017
   MONGODB_NAME=gitpulse
   POSTGRES_DB=gitpulse_new
   POSTGRES_USER=gitpulse_user
   POSTGRES_PASSWORD=your-secure-password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432

   # GitPulse Configuration
   INDEXING_SERVICE=github_api
   GITHUB_API_RATE_LIMIT_WARNING=10
   GITHUB_API_TIMEOUT=30

   # Ollama Configuration
   OLLAMA_HOST=http://localhost:11434
   OLLAMA_MODEL=llama3.2:3b

   # Django-Q Configuration
   Q_WORKERS=4
   Q_RECYCLE=500
   Q_TIMEOUT=3600
   Q_RETRY=4000
   Q_SAVE_LIMIT=250
   Q_QUEUE_LIMIT=500
   Q_CPU_AFFINITY=1

   # Cache Configuration
   CACHE_TIMEOUT=3600
   CACHE_MAX_ENTRIES=1000
   ANALYTICS_CACHE_TIMEOUT=3600
   PR_METRICS_CACHE_TIMEOUT=1800
   COMMIT_METRICS_CACHE_TIMEOUT=7200
   ```

### Method 2: Environment Variables

You can also define environment variables directly:

```bash
export DEBUG=True
export MONGODB_HOST=localhost
export POSTGRES_PASSWORD=your-secure-password
export INDEXING_SERVICE=github_api
```

### Method 3: Docker Environment

For Docker deployments, you can pass environment variables:

```bash
docker-compose up -d -e DEBUG=False -e MONGODB_HOST=mongodb
```

## 🔍 Configuration Priority

The configuration is loaded in the following order (highest to lowest priority):

1. **Environment variables** (highest priority)
2. **`.env` file**
3. **Default values** in the code (lowest priority)

## ✅ Testing Configuration

### Test Environment Variables

You can test if your configuration is loaded correctly:

```bash
# Test Django settings
python manage.py check

# Test specific settings
python -c "from django.conf import settings; print(f'DEBUG: {settings.DEBUG}')"
```

### Test Database Connections

```bash
# Test PostgreSQL
python manage.py dbshell

# Test MongoDB
python manage.py shell
```

Then in the shell:
```python
from mongoengine import connect
# Should connect without errors
```

## 🔐 Security Best Practices

### Production Configuration

For production environments:

1. **Use strong secret keys**
   ```env
   SECRET_KEY=your-very-long-and-random-secret-key
   ```

2. **Disable debug mode**
   ```env
   DEBUG=False
   ```

3. **Use secure database passwords**
   ```env
   POSTGRES_PASSWORD=very-secure-password-with-special-chars
   ```

4. **Restrict allowed hosts**
   ```env
   ALLOWED_HOSTS=your-domain.com,www.your-domain.com
   ```

### Environment-Specific Files

You can create environment-specific configuration files:

```bash
# Development
cp env.example .env.development

# Production
cp env.example .env.production

# Staging
cp env.example .env.staging
```

## 🚨 Troubleshooting

### Common Issues

**Configuration not loaded**
```bash
# Check if .env file exists
ls -la .env

# Check file permissions
chmod 600 .env
```

**Database connection issues**
```bash
# Test MongoDB connection
python -c "from mongoengine import connect; connect('gitpulse')"

# Test PostgreSQL connection
python manage.py dbshell
```

**Environment variables not recognized**
```bash
# Check if python-decouple is installed
pip list | grep decouple

# Restart your shell/terminal
source venv/bin/activate
```

## 📚 Related Documentation

- **[Quick Start Guide](quick-start.md)** - Get started quickly
- **[Installation Guide](installation.md)** - Detailed installation instructions
- **[Docker Guide](../deployment/docker.md)** - Docker-specific configuration
- **[Production Guide](../deployment/production.md)** - Production deployment configuration 