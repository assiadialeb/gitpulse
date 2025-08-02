#!/bin/bash

# GitPulse Documentation Deployment Script
# This script builds and deploys the documentation to GitHub Pages

set -e  # Exit on any error

echo "🚀 GitPulse Documentation Deployment"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "mkdocs.yml" ]; then
    print_error "mkdocs.yml not found. Please run this script from the GitPulse root directory."
    exit 1
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    print_warning "Virtual environment not detected. Attempting to activate..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        print_error "Virtual environment not found. Please create one first:"
        echo "  python -m venv venv"
        echo "  source venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
fi

# Check if required packages are installed
print_status "Checking dependencies..."
if ! python -c "import mkdocs" 2>/dev/null; then
    print_error "MkDocs not found. Installing..."
    pip install mkdocs mkdocs-material mkdocs-git-revision-date-localized-plugin
fi

# Build documentation
print_status "Building documentation..."
if mkdocs build; then
    print_status "Documentation built successfully!"
else
    print_error "Build failed!"
    exit 1
fi

# Check if ghp-import is available
if ! command -v ghp-import &> /dev/null; then
    print_status "Installing ghp-import..."
    pip install ghp-import
fi

# Deploy to GitHub Pages
print_status "Deploying to GitHub Pages..."
if ghp-import -n -p -f site/; then
    print_status "Deployment successful!"
    echo ""
    echo "🎉 Documentation deployed to GitHub Pages!"
    echo "📖 Your documentation should be available at:"
    echo "   https://assiadialeb.github.io/gitpulse"
    echo ""
    echo "Note: It may take a few minutes for the changes to appear."
else
    print_error "Deployment failed!"
    exit 1
fi

print_status "Deployment complete!" 