# GitPulse – Functional Overview

## 🔎 What is GitPulse?

**GitPulse** is an open-source analytics dashboard designed for CTOs, tech leads, and curious developers who want to better understand developer activity and contribution trends within their GitHub organizations.

The platform connects to a GitHub organization via OAuth2, collects commit and pull request data across all repositories, and stores them for visualization and analysis. GitPulse provides visibility into coding velocity, collaboration patterns, and code health — all from a single interface.

---

## 🧰 Tech Stack

| Component        | Description                                |
|------------------|--------------------------------------------|
| **Backend**      | Django (Python 3.12+)                      |
| **Database**     | MongoDB (via `mongoengine` or similar)     |
| **Auth**         | Django built-in auth + OAuth2 (GitHub App) |
| **Storage**      | Commits, PRs, and user activity in MongoDB |
| **API**          | GitHub REST API v3                         |
| **Infra**        | Docker-based local setup                   |
| **Front**        | Django template, DaisyUI                   |
---

## 🔐 Features

### 1. User Authentication

- Simple user login/registration (via Django auth)
- Dashboard access restricted to authenticated users
- Token-based session support (to be added for API use)

---

### 2. GitHub App Integration (OAuth2)

- Each user can connect GitPulse to their GitHub account via a GitHub App
- OAuth2 flow used to retrieve a token with access to:
  - Repositories (read-only)
  - Commits and PRs
  - Organization membership (if needed)

- GitPulse stores relevant user GitHub metadata and access tokens securely
- One GitHub App installation per user or org

---

### 3. Dashboard

- Overview of GitHub activity per user or repository
- Key metrics:
  - Number of commits per developer / per repo
  - Active hours (commit heatmap)
  - Average lines added/removed per PR
  - Merge delay (from PR open → merge)
  - Branch and tag trends

- Future roadmap:
  - Leaderboards and developer trends
  - Team-level aggregation
  - Custom report generation

---

## 📦 Project Structure (WIP)
gitpulse/
├── config/           # Django settings and URL routing
├── core/             # Main Django app for logic
├── users/            # Auth and profile logic
├── github_sync/      # GitHub integration, API sync jobs
├── templates/        # HTML templates
├── static/           # Front-end assets (if needed)
├── manage.py

---

## 🧭 Roadmap (Upcoming Features)

- GitHub webhook support for real-time updates
- Scheduled background jobs to sync commits
- Export dashboards as CSV/PDF
- Integration with Slack or email for notifications
- Tagging of commits (e.g., feature, bugfix, refactor)

---

## 📝 License

GitPulse is released under the **GNU Affero General Public License v3.0 (AGPLv3)** to ensure that all usage, even in SaaS form, preserves the project's open nature.