#!/bin/bash

# GitPulse Documentation Deployment Script
# This script builds and deploys the documentation to GitHub Pages

set -e

echo "🚀 Building GitPulse documentation..."

# Build the documentation
python3 -m mkdocs build

echo "✅ Documentation built successfully"

# Check if we're on the main branch
if [ "$(git branch --show-current)" != "main" ]; then
    echo "⚠️  Warning: Not on main branch. Deployment will still work but consider switching to main."
fi

# Commit and push changes
echo "📝 Committing changes..."
git add .
git commit -m "Update documentation and configuration" || echo "No changes to commit"

echo "🚀 Pushing to GitHub..."
git push

echo "✅ Deployment triggered!"
echo "📖 Your site will be available at: https://assiadialeb.github.io"
echo "⏱️  It may take 5-10 minutes for changes to appear." 