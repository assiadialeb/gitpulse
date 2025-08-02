# Installation Guide

This guide covers all installation methods for GitPulse, from Docker to local development setup.

## 🐳 Docker Installation (Recommended)

### Prerequisites

- Docker and Docker Compose installed
- Git installed
- At least 4GB of RAM available
- 10GB of free disk space

### Step 1: Clone Repository

```bash
git clone https://github.com/gitpulse/gitpulse.git
cd GitPulse
```

### Step 2: Environment Configuration

Create a `.env` file at the project root:

```bash
cp env.example .env
```

Edit the `.env` file according to your needs:

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

### Step 3: Start Services

```bash
# Build and start all services
docker-compose up -d --build
```

This command will:
- Build the Docker image for the application
- Start PostgreSQL (Django database)
- Start MongoDB (analytics database)
- Start Redis (cache)
- Start Ollama (AI for commit classification)
- Start the Django application

### Step 4: Verify Services

```bash
docker-compose ps
```

You should see all services with "Up" status.

### Step 5: Initialize Database

```bash
# Create Django migrations
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser
```

### Step 6: Collect Static Files

```bash
docker-compose exec web python manage.py collectstatic --noinput
```

### Step 7: Access the Application

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## 🖥️ Local Installation

### Prerequisites

- Python 3.12+
- PostgreSQL (recommended) or SQLite
- MongoDB
- Git

### Step 1: Clone Repository

```bash
git clone https://github.com/gitpulse/gitpulse.git
cd GitPulse
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
cp env.example .env
# Edit .env with your database settings
```

### Step 5: Install and Configure Databases

#### PostgreSQL

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser gitpulse_user
sudo -u postgres createdb gitpulse_new
sudo -u postgres psql -c "ALTER USER gitpulse_user PASSWORD 'gitpulse_password';"
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
createdb gitpulse_new
```

**Windows:**
Download and install from [PostgreSQL website](https://www.postgresql.org/download/windows/)

#### MongoDB

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install mongodb
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

**macOS:**
```bash
brew install mongodb-community
brew services start mongodb-community
```

**Windows:**
Download and install from [MongoDB website](https://www.mongodb.com/try/download/community)

### Step 6: Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 7: Create Superuser

```bash
python manage.py createsuperuser
```

### Step 8: Start Development Server

```bash
python manage.py runserver
```

### Step 9: Access the Application

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## 🔧 Development Setup

### Additional Development Tools

```bash
# Install development dependencies
pip install -r requirements-dev.txt  # if available

# Install pre-commit hooks
pre-commit install

# Install additional tools
pip install black isort flake8 mypy
```

### Database Setup for Development

```bash
# Create test database
createdb gitpulse_test

# Run tests
python manage.py test

# Load sample data (if available)
python manage.py loaddata sample_data.json
```

## 🚀 Production Installation

### Prerequisites

- Linux server (Ubuntu 20.04+ recommended)
- Docker and Docker Compose
- Nginx (for reverse proxy)
- SSL certificate (Let's Encrypt recommended)

### Step 1: Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Step 2: Clone and Configure

```bash
git clone https://github.com/gitpulse/gitpulse.git
cd GitPulse
cp env.example .env
```

### Step 3: Production Configuration

Edit `.env` for production:

```env
DEBUG=False
SECRET_KEY=your-very-long-and-random-secret-key
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Use external databases for production
POSTGRES_HOST=your-postgres-host
POSTGRES_PASSWORD=very-secure-password
MONGODB_HOST=your-mongodb-host
```

### Step 4: Deploy

```bash
# Build and start
docker-compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Step 5: Configure Nginx

Create Nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔐 Security Considerations

### Production Security

1. **Use strong passwords**
   ```env
   POSTGRES_PASSWORD=very-long-random-password-with-special-chars
   ```

2. **Disable debug mode**
   ```env
   DEBUG=False
   ```

3. **Use HTTPS**
   - Configure SSL certificates
   - Redirect HTTP to HTTPS

4. **Restrict database access**
   - Use firewall rules
   - Configure database authentication

5. **Regular updates**
   - Keep dependencies updated
   - Monitor security advisories

### Environment Variables Security

```bash
# Set file permissions
chmod 600 .env

# Use environment-specific files
cp env.example .env.production
```

## 🚨 Troubleshooting

### Common Issues

**Port conflicts**
```bash
# Check what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

**Database connection issues**
```bash
# Test PostgreSQL
psql -h localhost -U gitpulse_user -d gitpulse_new

# Test MongoDB
mongo localhost:27017/gitpulse
```

**Permission issues**
```bash
# Fix file permissions
chmod +x manage.py
chmod 600 .env
```

**Docker issues**
```bash
# Clean up Docker
docker system prune -a

# Rebuild containers
docker-compose down
docker-compose up -d --build
```

### Getting Help

- Check the [Troubleshooting Guide](technical/troubleshooting.md)
- Review the [Configuration Guide](configuration.md)
- Open an [issue on GitHub](https://github.com/gitpulse/gitpulse/issues)

## 📚 Next Steps

- **[Configuration Guide](configuration.md)** - Configure your installation
- **[Quick Start Guide](quick-start.md)** - Get started quickly
- **[User Guide](user-guide/overview.md)** - Learn how to use GitPulse
- **[Deployment Guide](deployment/production.md)** - Production deployment 