# GitPulse - GitHub Analytics Dashboard

**GitHub Analytics Dashboard for CTOs, Tech Leads, and Curious Developers**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2+-blue.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)

# 🧭 What is GitPulse?

**GitPulse** is an open-source dashboard designed to analyze developer activity and contribution trends within a GitHub organization.

I started building it as a **CTO** because I couldn't find a tool that was simple and reliable enough to track the activity of my teams and products. GitPulse is a **personal project**, developed during my free time. It will evolve based on my availability and interests.

I'm currently building GitPulse **solo**, with no QA team. If you encounter bugs or unexpected behavior, **contributions are welcome**—as long as they stay aligned with the spirit of the project: useful, readable, and not overengineered.

---

## ✨ Key Features

- 📊 **Comprehensive Analytics**: Track commits, pull requests, reviews, and more
- 👥 **Developer Insights**: Understand individual and team activity patterns
- 📈 **Trend Analysis**: Visualize contribution trends and detect slowdowns
- 🔍 **Repository Analytics**: Detailed view of code activity and quality
- ⚡ **Real-time Updates**: Live data pulled from GitHub APIs
- 🎯 **Custom Metrics**: Define and track your own KPIs

---

## 🎯 Who is it for?

- **CTOs** who want a clear view of team productivity and project health
- **Tech Leads** aiming to optimize engineering workflows
- **Project Managers / POs** tracking delivery progress and team dynamics
- **Developers** curious about their own or their team's contribution patterns
- **Open Source Maintainers** monitoring community activity

---

## 🏗️ Architecture (briefly)

GitPulse uses a modern but focused tech stack:

- **Backend**: Django 5.2+ (Python 3.12)
- **Databases**: MongoDB (analytics data) + PostgreSQL (user data)
- **Task Queue**: Django-Q
- **UI**: Responsive frontend with DaisyUI
- **Deployment**: Docker-ready with clean documentation

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
- SBOM generation with [@cyclonedx/cdxgen](https://github.com/CycloneDX/cdxgen)

---

**Made with ❤️ for the developer community**

[GitHub](https://github.com/assiadialeb/gitpulse) • [Issues](https://github.com/assiadialeb/gitpulse/issues) • [Discussions](https://github.com/assiadialeb/gitpulse/discussions) 