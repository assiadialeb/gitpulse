# GitHub Pages Deployment

This guide explains how to deploy the GitPulse documentation to GitHub Pages using MkDocs.

## 🚀 Quick Deployment

### Prerequisites

- Git repository on GitHub
- MkDocs and Material theme installed
- GitHub Actions enabled (optional)

### Step 1: Build Documentation

```bash
# Build the documentation
mkdocs build

# Test locally
mkdocs serve
```

### Step 2: Deploy to GitHub Pages

#### Option 1: Manual Deployment

```bash
# Install ghp-import
pip install ghp-import

# Deploy to GitHub Pages
ghp-import -n -p -f site/
```

#### Option 2: GitHub Actions (Recommended)

Create `.github/workflows/docs.yml`:

```yaml
name: Deploy Documentation

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install mkdocs mkdocs-material mkdocs-git-revision-date-localized-plugin
    
    - name: Build documentation
      run: mkdocs build
    
    - name: Deploy to GitHub Pages
      if: github.ref == 'refs/heads/main'
      uses: peaceiris/actions-gh-pages@v3
      with:
        github_token: ${{ secrets.GITHUB_TOKEN }}
        publish_dir: ./site
```

## 🔧 Configuration

### Repository Settings

1. **Enable GitHub Pages**
   - Go to repository Settings > Pages
   - Source: Deploy from a branch
   - Branch: `gh-pages` (created by ghp-import)
   - Folder: `/ (root)`

2. **Configure Custom Domain** (Optional)
   - Add custom domain in repository settings
   - Create `CNAME` file in `docs/` directory

### MkDocs Configuration

Update `mkdocs.yml` for GitHub Pages:

```yaml
site_name: GitPulse
site_description: GitHub Analytics Dashboard for CTOs and Tech Leads
site_author: GitPulse Team
site_url: https://your-username.github.io/gitpulse

repo_name: your-username/gitpulse
repo_url: https://github.com/your-username/gitpulse
edit_uri: edit/main/docs/

theme:
  name: material
  palette:
    - media: "(prefers-color-scheme)"
      scheme: default
      primary: green
      accent: blue
      toggle:
        icon: material/brightness-auto
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: green
      accent: blue
      toggle:
        icon: material/brightness-7
        name: Switch to light mode
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - search.suggest
    - search.highlight
    - content.code.copy
  icon:
    repo: fontawesome/brands/github
    edit: material/pencil
    view: material/eye

plugins:
  - search
  - git-revision-date-localized:
      enable_creation_date: true

markdown_extensions:
  - abbr
  - admonition
  - attr_list
  - def_list
  - footnotes
  - md_in_html
  - toc:
      permalink: true
  - pymdownx.betterem:
      smart_enable: all
  - pymdownx.caret
  - pymdownx.details
  - pymdownx.emoji:
      emoji_generator: !!python/name:material.extensions.emoji.to_svg
      emoji_index: !!python/name:material.extensions.emoji.twemoji
  - pymdownx.highlight:
      anchor_linenums: true
      line_spans: __span
      pygments_lang_class: true
  - pymdownx.inlinehilite
  - pymdownx.keys
  - pymdownx.magiclink
  - pymdownx.mark
  - pymdownx.smartsymbols
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.tasklist:
      custom_checkbox: true
  - pymdownx.tilde

nav:
  - Home: index.md
  - Getting Started:
    - Quick Start: getting-started/quick-start.md
    - Installation: getting-started/installation.md
    - Configuration: getting-started/configuration.md
  - User Guide:
    - Overview: user-guide/overview.md
    - GitHub Setup: user-guide/github-setup.md
    - Projects: user-guide/projects.md
    - Analytics: user-guide/analytics.md
    - Developers: user-guide/developers.md
  - Technical Documentation:
    - Architecture: technical/architecture.md
    - API Reference: technical/api.md
    - Management Commands: technical/management-commands.md
    - Troubleshooting: technical/troubleshooting.md
  - Deployment:
    - Docker: deployment/docker.md
    - Production: deployment/production.md
    - GitHub Pages: deployment/github-pages.md

extra:
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/your-username/gitpulse
```

## 📝 Documentation Structure

### Recommended Structure

```
docs/
├── index.md                    # Home page
├── getting-started/
│   ├── quick-start.md         # Quick start guide
│   ├── installation.md        # Installation guide
│   └── configuration.md       # Configuration guide
├── user-guide/
│   ├── overview.md            # User overview
│   ├── github-setup.md        # GitHub setup
│   ├── projects.md            # Projects guide
│   ├── analytics.md           # Analytics guide
│   └── developers.md          # Developers guide
├── technical/
│   ├── architecture.md        # Technical architecture
│   ├── api.md                 # API reference
│   ├── management-commands.md # Management commands
│   └── troubleshooting.md     # Troubleshooting
└── deployment/
    ├── docker.md              # Docker deployment
    ├── production.md          # Production deployment
    └── github-pages.md        # This guide
```

### Content Guidelines

1. **Use clear headings**
   ```markdown
   # Main Title
   ## Section Title
   ### Subsection Title
   ```

2. **Include code examples**
   ```markdown
   ```bash
   # Command example
   mkdocs build
   ```
   ```

3. **Add navigation links**
   ```markdown
   - **[Next Step](next-page.md)** - Description
   - **[Previous Step](prev-page.md)** - Description
   ```

4. **Use admonitions**
   ```markdown
   !!! note "Note"
       This is an important note.

   !!! warning "Warning"
       This is a warning.

   !!! tip "Tip"
       This is a helpful tip.
   ```

## 🔄 Continuous Deployment

### GitHub Actions Workflow

Create `.github/workflows/docs.yml`:

```yaml
name: Deploy Documentation

on:
  push:
    branches: [ main ]
    paths: [ 'docs/**', 'mkdocs.yml' ]
  pull_request:
    branches: [ main ]
    paths: [ 'docs/**', 'mkdocs.yml' ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install mkdocs mkdocs-material mkdocs-git-revision-date-localized-plugin
    
    - name: Build documentation
      run: mkdocs build
    
    - name: Check links
      run: |
        pip install linkchecker
        linkchecker site/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install mkdocs mkdocs-material mkdocs-git-revision-date-localized-plugin
    
    - name: Build documentation
      run: mkdocs build
    
    - name: Deploy to GitHub Pages
      uses: peaceiris/actions-gh-pages@v3
      with:
        github_token: ${{ secrets.GITHUB_TOKEN }}
        publish_dir: ./site
        force_orphan: true
```

### Manual Deployment Script

Create `deploy-docs.sh`:

```bash
#!/bin/bash

# Build documentation
echo "Building documentation..."
mkdocs build

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "Build successful!"
    
    # Deploy to GitHub Pages
    echo "Deploying to GitHub Pages..."
    ghp-import -n -p -f site/
    
    echo "Deployment complete!"
    echo "Your documentation is available at: https://your-username.github.io/gitpulse"
else
    echo "Build failed!"
    exit 1
fi
```

Make it executable:
```bash
chmod +x deploy-docs.sh
```

## 🎨 Customization

### Custom CSS

Create `docs/stylesheets/extra.css`:

```css
/* Custom styles */
.md-header {
    background-color: #4CAF50;
}

.md-nav__title {
    color: #4CAF50;
}

.md-footer {
    background-color: #f5f5f5;
}
```

### Custom JavaScript

Create `docs/javascripts/extra.js`:

```javascript
// Custom JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Add custom functionality
    console.log('GitPulse documentation loaded');
});
```

### Custom Theme

```yaml
theme:
  name: material
  custom_dir: overrides
  static_templates:
    - 404.html
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - search.suggest
    - search.highlight
    - content.code.copy
  palette:
    - media: "(prefers-color-scheme)"
      scheme: default
      primary: green
      accent: blue
      toggle:
        icon: material/brightness-auto
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: green
      accent: blue
      toggle:
        icon: material/brightness-7
        name: Switch to light mode
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Build Failures

```bash
# Check MkDocs version
mkdocs --version

# Update MkDocs
pip install --upgrade mkdocs mkdocs-material

# Check configuration
mkdocs build --strict
```

#### 2. Deployment Issues

```bash
# Check if ghp-import is installed
pip install ghp-import

# Force deployment
ghp-import -n -p -f site/ --force

# Check GitHub Pages settings
# Go to repository Settings > Pages
```

#### 3. Custom Domain Issues

```bash
# Create CNAME file
echo "your-domain.com" > docs/CNAME

# Check DNS settings
dig your-domain.com
```

### Debug Commands

```bash
# Test build locally
mkdocs build

# Serve locally
mkdocs serve

# Check links
linkchecker site/

# Validate HTML
html5validator site/
```

## 📚 Next Steps

- **[Docker Deployment](docker.md)** - Deploy the application with Docker
- **[Production Deployment](production.md)** - Production deployment guide
- **[Configuration Guide](getting-started/configuration.md)** - Application configuration
- **[Troubleshooting Guide](technical/troubleshooting.md)** - Common issues and solutions 