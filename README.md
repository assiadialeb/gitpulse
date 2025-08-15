# GitPulse - GitHub Analytics Dashboard

GitPulse is an open-source analytics dashboard designed for CTOs, tech leads, and curious developers who want to better understand developer activity and contribution trends within their GitHub organizations.

🚨 **GitPulse is under alpha dev process, i can introduce breaking changes**

[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=assiadialeb_gitpulse&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=assiadialeb_gitpulse) [![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=assiadialeb_gitpulse&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=assiadialeb_gitpulse) [![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=assiadialeb_gitpulse&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=assiadialeb_gitpulse)

📄 [Documentation](https://assiadialeb.github.io/gitpulse/)

## 🚀 Quick Start

### Option 1: Docker (Recommended)

**Prerequisites**: Docker and Docker Compose

1. **Clone and start**

   ```bash
   git clone https://github.com/assiadialeb/gitpulse.git
   cd GitPulse
   cp env.example .env
   docker-compose up -d --build
   ```
2. **Initialize**

   ```bash
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py createsuperuser
   ```
3. **Access the application**

   - Open http://localhost:8000
   - Login with your superuser credentials

📖 **See [Docker Quick Start](docs/getting-started/quick-start.md) for detailed instructions**

### Option 2: Local Installation

**Prerequisites**:

- Python 3.12+
- PostgreSQL (recommended) or SQLite
- MongoDB
- Redis
- Git

1. **Clone the repository**

   ```bash
   git clone https://github.com/assiadialeb/gitpulse.git
   cd GitPulse
   ```
2. **Create virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment**

   ```bash
   cp env.example .env
   # Edit .env with your database settings
   ```
5. **Run migrations**

   ```bash
   python manage.py migrate
   ```
6. **Create superuser**

   ```bash
   python manage.py createsuperuser
   ```
7. **Start the server**

   ```bash
   python manage.py runserver
   ```
8. **Access the application**

   - Open http://localhost:8000
   - Login with your superuser credentials

## 📚 Documentation

Comprehensive documentation is available at: **https://assiadialeb.github.io/gitpulse/**

### Local Documentation Development

```bash
# Install MkDocs
pip install mkdocs mkdocs-material

# Serve documentation locally
mkdocs serve

# Build documentation
mkdocs build

# Deploy to GitHub Pages
./deploy-docs.sh
```

## ⚙️ Environment Configuration

GitPulse uses `python-decouple` to manage configuration through environment variables. All settings can be configured via the `.env` file.

### Key Configuration Variables

#### Django Core

- `DEBUG`: Enable/disable debug mode (default:`True`)
- `SECRET_KEY`: Django secret key for security
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `LANGUAGE_CODE`: Language code (default:`en-us`)
- `TIME_ZONE`: Timezone (default:`Europe/Paris`)

#### Database Configuration

- `MONGODB_HOST`: MongoDB host (default:`localhost`)
- `MONGODB_PORT`: MongoDB port (default:`27017`)
- `MONGODB_NAME`: MongoDB database name (default:`gitpulse`)
- `POSTGRES_DB`: PostgreSQL database name (default:`gitpulse_new`)
- `POSTGRES_USER`: PostgreSQL username (default:`gitpulse_user`)
- `POSTGRES_PASSWORD`: PostgreSQL password (default:`gitpulse_password`)
- `POSTGRES_HOST`: PostgreSQL host (default:`localhost`)
- `POSTGRES_PORT`: PostgreSQL port (default:`5432`)

#### GitPulse Configuration

- `INDEXING_SERVICE`: Choose indexing service (`git_local` or`github_api`)
- `GITHUB_API_RATE_LIMIT_WARNING`: Rate limit warning threshold (default:`10`)
- `GITHUB_API_TIMEOUT`: API timeout in seconds (default:`30`)

#### Ollama Configuration

- `OLLAMA_HOST`: Ollama server URL (default:`http://localhost:11434`)
- `OLLAMA_MODEL`: Ollama model name (default:`llama3.2:3b`)

#### Django-Q Configuration

- `Q_WORKERS`: Number of worker processes (default:`4`)
- `Q_RECYCLE`: Worker recycle count (default:`500`)
- `Q_TIMEOUT`: Task timeout in seconds (default:`3600`)
- `Q_RETRY`: Retry count (default:`4000`)
- `Q_SAVE_LIMIT`: Save limit (default:`250`)
- `Q_QUEUE_LIMIT`: Queue limit (default:`500`)
- `Q_CPU_AFFINITY`: CPU affinity (default:`1`)

#### Cache Configuration

- `CACHE_TIMEOUT`: Cache timeout in seconds (default:`3600`)
- `CACHE_MAX_ENTRIES`: Maximum cache entries (default:`1000`)
- `ANALYTICS_CACHE_TIMEOUT`: Analytics cache timeout (default:`3600`)
- `PR_METRICS_CACHE_TIMEOUT`: PR metrics cache timeout (default:`1800`)
- `COMMIT_METRICS_CACHE_TIMEOUT`: Commit metrics cache timeout (default:`7200`)

### Example .env file

```bash
# Copy env.example to .env and customize as needed
cp env.example .env
```

## 🏗️ Architecture

- **Backend**: Django (Python 3.12+)
- **Database**: SQLite (auth) + MongoDB (GitHub data)
- **Frontend**: Django templates + DaisyUI
- **Authentication**: Django auth + GitHub OAuth2
- **API**: GitHub REST API v3

## 📁 Project Structure

```
GitPulse/
├── config/           # Django settings and URL routing
├── users/            # Authentication and user management
├── github/           # GitHub OAuth2 integration
├── templates/        # HTML templates
├── static/           # Static files
├── docs/             # Documentation
├── manage.py         # Django management script
└── setup_github_app.py  # GitHub App setup script
```

## 🔧 Development

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Accessing Admin

- URL: http://localhost:8000/admin/
- Use your superuser credentials

## 📊 Features

### Current Features

- ✅ User authentication (login/register)
- ✅ GitHub App integration for github API
- ✅ GitHub Oauth2 integration for github SSO
- ✅ Dashboard with connection status
- ✅ GitHub App configuration
- ✅ Token management

### Planned Features

- 🔄 GitHub data synchronization
- 📈 Analytics dashboard
- 📊 Repository statistics
- 👥 Team analytics
- 📋 Custom reports

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the GNU Affero General Public License v3.0 (AGPLv3).

## 🆘 Support

If you encounter any issues:

1. Check the[documentation](ttps://assiadialeb.github.io/gitpulse/)
2. Search existing issues
3. Create a new issue with detailed information
4. [Discuss](https://github.com/assiadialeb/gitpulse/discussions) with the community
