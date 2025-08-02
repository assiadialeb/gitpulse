# Quick Start Guide

Get GitPulse up and running in minutes with our quick start guide.

## 🐳 Option 1: Docker (Recommended)

### Prerequisites

- Docker and Docker Compose installed
- Git

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

This will start all required services:
- **PostgreSQL**: Django database
- **MongoDB**: Analytics database  
- **Redis**: Cache and task queue
- **Ollama**: AI for commit classification
- **Django**: Web application

### Step 3: Initialize

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

### Step 4: Access

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## 🖥️ Option 2: Local Installation

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

### Step 5: Run Migrations

```bash
python manage.py migrate
```

### Step 6: Create Superuser

```bash
python manage.py createsuperuser
```

### Step 7: Start Server

```bash
python manage.py runserver
```

### Step 8: Access

- **Application**: http://localhost:8000
- **Admin**: http://localhost:8000/admin

## 🔧 Essential Commands

### Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Django shell
docker-compose exec web python manage.py shell

# PostgreSQL shell
docker-compose exec postgres psql -U gitpulse -d gitpulse
```

### Local Commands

```bash
# Start development server
python manage.py runserver

# Run tests
python manage.py test

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Django shell
python manage.py shell
```

## 🔐 GitHub Configuration

### Step 1: Create GitHub OAuth App

1. Go to [GitHub Apps settings](https://github.com/settings/apps)
2. Click "New GitHub App"
3. Fill in the app details:
   - **App name**: GitPulse (or your preferred name)
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:8000/github/oauth/callback/`
4. Set permissions:
   - **Repository permissions**: Contents (Read)
   - **User permissions**: Email addresses (Read)
5. Click "Create GitHub App"

### Step 2: Configure GitPulse

1. Copy the Client ID and Client Secret from your GitHub App
2. Add them to your `.env` file:
   ```bash
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   ```
3. Restart the application:
   ```bash
   # Docker
   docker-compose restart web
   
   # Local
   python manage.py runserver
   ```

## 🚨 Troubleshooting

### Common Issues

**Ports already in use**
```bash
# Check what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

**Database connection issues**
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres
```

**Permission issues**
```bash
# Fix file permissions
chmod +x manage.py
```

### Getting Help

- Check the [Troubleshooting Guide](technical/troubleshooting.md)
- Review the [Configuration Guide](getting-started/configuration.md)
- Open an [issue on GitHub](https://github.com/gitpulse/gitpulse/issues)

## 📚 Next Steps

- **[Installation Guide](installation.md)** - Detailed installation instructions
- **[Configuration Guide](configuration.md)** - Environment and application configuration
- **[User Guide](user-guide/overview.md)** - How to use GitPulse features
- **[GitHub Setup](user-guide/github-setup.md)** - Complete GitHub integration guide 