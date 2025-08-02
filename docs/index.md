# GitPulse - GitHub Analytics Dashboard

**GitHub Analytics Dashboard for CTOs, Tech Leads, and Curious Developers**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2+-blue.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)

## 🚀 What is GitPulse?

GitPulse is an open-source analytics dashboard designed to help CTOs, tech leads, and developers better understand developer activity and contribution trends within their GitHub organizations.

### ✨ Key Features

- **📊 Comprehensive Analytics**: Track commits, pull requests, code reviews, and more
- **👥 Developer Insights**: Understand individual and team performance patterns
- **📈 Trend Analysis**: Identify productivity trends and bottlenecks
- **🔍 Deep Repository Analysis**: Detailed insights into code quality and activity
- **⚡ Real-time Updates**: Live data from GitHub APIs
- **🎯 Custom Metrics**: Define and track your own KPIs

### 🎯 Who is it for?

- **CTOs** looking to understand team productivity and project health
- **Tech Leads** wanting to optimize development processes
- **Project Managers** tracking project progress and team performance
- **Developers** curious about their own and team's contribution patterns
- **Open Source Maintainers** monitoring community activity

## 🏗️ Architecture

GitPulse is built with modern technologies:

- **Backend**: Django 5.2+ with Python 3.12+
- **Database**: MongoDB for analytics data, PostgreSQL for user data
- **Task Queue**: Django-Q for background processing
- **Frontend**: Modern responsive UI with DaisyUI
- **Deployment**: Docker-ready with comprehensive documentation

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/assiadialeb/gitpulse.git
cd GitPulse
cp env.example .env
docker-compose up -d --build
```

### Option 2: Local Installation

```bash
git clone https://github.com/assiadialeb/gitpulse.git
cd GitPulse
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env
python manage.py migrate
python manage.py runserver
```

## 📚 Documentation

- **[Getting Started](getting-started/quick-start.md)** - Quick setup guide
- **[User Guide](user-guide/overview.md)** - How to use GitPulse
- **[Technical Docs](technical/architecture.md)** - Architecture and API reference
- **[Deployment](deployment/docker.md)** - Production deployment guide

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
git clone https://github.com/assiadialeb/gitpulse.git
cd GitPulse
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
python manage.py migrate
python manage.py runserver
```

## 📄 License

This project is licensed under the AGPL v3 License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Django](https://djangoproject.com)
- UI powered by [DaisyUI](https://daisyui.com)
- Documentation with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)

---

**Made with ❤️ for the developer community**

[GitHub](https://github.com/assiadialeb/gitpulse) • [Issues](https://github.com/assiadialeb/gitpulse/issues) • [Discussions](https://github.com/assiadialeb/gitpulse/discussions) 