# GitPulse - GitHub Analytics Dashboard

GitPulse is an open-source analytics dashboard designed for CTOs, tech leads, and curious developers who want to better understand developer activity and contribution trends within their GitHub organizations.

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- MongoDB (optional, for future GitHub data storage)
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
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

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

6. **Start the server**
   ```bash
   python manage.py runserver
   ```

7. **Access the application**
   - Open http://localhost:8000
   - Login with your superuser credentials

## 🔐 GitHub OAuth2 Setup

GitPulse uses OAuth2 to connect to GitHub. You need to create a GitHub App and configure it with GitPulse.

### Step 1: Create a GitHub App

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

**Option A: Use the setup script (Recommended)**
```bash
python setup_github_app.py
```

**Option B: Manual configuration**
1. Go to http://localhost:8000/github/admin/ (superuser only)
2. Enter your GitHub App credentials:
   - Client ID (found in your GitHub App settings)
   - Client Secret (generate a new one)
   - App ID (found in your GitHub App settings)

### Step 3: Connect Your Account

1. Go to http://localhost:8000/github/setup/
2. Click "Connect to GitHub"
3. Authorize GitPulse to access your GitHub account
4. You'll be redirected back to GitPulse with your account connected

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
- ✅ GitHub OAuth2 integration
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

1. Check the [documentation](docs/)
2. Search existing issues
3. Create a new issue with detailed information

## 🔗 Links

- [GitHub OAuth Apps Documentation](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps)
- [Django Documentation](https://docs.djangoproject.com/)
- [DaisyUI Documentation](https://daisyui.com/)
