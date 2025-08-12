# Contributing to GitPulse

First off, thank you for your interest in contributing to **GitPulse**!  
We welcome contributions from CTOs, tech leads, curious developers, and anyone passionate about open source analytics for GitHub activity.

This guide will help you get started with your first contribution and understand how we work together.

---

## 📜 Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).  
By participating, you are expected to uphold this code. Please report unacceptable behavior to **maintainers@gitpulse.io**.

---

## 🚀 Ways to Contribute

You can contribute in many ways, including:

- **Reporting bugs** (please use the bug report template).
- **Suggesting features** (open an issue before starting work to discuss).
- **Improving documentation**.
- **Writing or improving tests**.
- **Refactoring code** or optimizing performance.
- **Adding translations** if applicable.

---

## 🛠 Contribution Process

1. **Fork** the repository to your GitHub account.
2. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following our coding style and conventions.
4. **Add or update tests** if needed.
5. **Run the test suite** to ensure everything works:
   ```bash
   pytest
   ```
6. **Commit** your changes with a clear message (we use [Conventional Commits](https://www.conventionalcommits.org/)):
   ```bash
   git commit -m "feat: add SBOM component parsing"
   ```
7. **Push** your branch and open a Pull Request (PR) against the `main` branch.
8. **Describe your changes** in the PR and link any related issues (e.g., `Fixes #123`).
9. Wait for a **code review** — we aim for constructive, respectful feedback.

---

## 💻 Development Environment

**Requirements:**
- Python 3.11+
- Django 5+
- MongoDB or Redis
- Git
- `pip` or `poetry` for dependencies

**Setup:**
```bash
git clone https://github.com/your-org/gitpulse.git
cd gitpulse
cp .env.example .env  # configure environment variables
pip install -r requirements.txt
```

**Run the project:**
```bash
python manage.py runserver
```

**Run tests:**
```bash
pytest
```

---

## 📐 Coding Guidelines

- We use **Black**, **isort**, and **flake8** for formatting and linting.
- Branch naming convention:  
  - `feature/short-description`
  - `fix/issue-number`
- Commit messages follow **Conventional Commits**:
  - `feat:` for new features
  - `fix:` for bug fixes
  - `docs:` for documentation
  - `test:` for adding tests
  - `refactor:` for code restructuring without changing behavior
- All Python functions and classes must have **docstrings**.

---

## 🔄 Testing and CI/CD

- All contributions must pass the test suite.
- We use GitHub Actions to run automated tests on every PR.
- PRs with failing tests will not be merged.
- We aim for **high code coverage**; new features should come with tests.

---

## ⚖️ Licensing and Legal Notice

By contributing to this repository, you agree that:

- Your contributions will be licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
- You retain copyright to your work.
- You grant the maintainers the right to redistribute and modify it under the AGPL v3.
- You certify that your contributions are your own work or you have the right to submit them.

If you are contributing on behalf of a company, make sure you have permission to do so.

---

## 🔒 Privacy and Data Usage

GitPulse analyzes GitHub data. To respect privacy:

- Do not commit personal data or private API tokens.
- Use anonymized or mock datasets for tests.
- Test against sandbox or secondary GitHub accounts when possible.

---

## 📚 Resources

- [GitHub API Documentation](https://docs.github.com/en/rest)
- [Issues Board](https://github.com/your-org/gitpulse/issues)
- [Project Roadmap](ROADMAP.md)

---

**Thank you for making GitPulse better!**  
Every contribution — big or small — helps improve the tool for the entire community.
