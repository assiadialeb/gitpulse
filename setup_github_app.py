#!/usr/bin/env python3
"""
GitHub App Setup Script for GitPulse

This script helps you set up a GitHub App for OAuth2 authentication with GitPulse.
Follow the instructions to create your GitHub App and configure GitPulse.
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from github.models import GitHubApp
from django.contrib.auth.models import User

def print_header():
    """Print script header"""
    print("=" * 60)
    print("GitPulse - GitHub App Setup")
    print("=" * 60)
    print()

def print_instructions():
    """Print GitHub App creation instructions"""
    print("📋 STEP 1: Create a GitHub App")
    print("-" * 40)
    print("1. Go to: https://github.com/settings/apps")
    print("2. Click 'New GitHub App'")
    print("3. Fill in the following details:")
    print()
    print("   App name: GitPulse (or your preferred name)")
    print("   Homepage URL: http://localhost:8000")
    print("   Authorization callback URL: http://localhost:8000/github/oauth/callback/")
    print()
    print("4. Set permissions:")
    print("   - Repository permissions: Contents (Read)")
    print("   - User permissions: Email addresses (Read)")
    print()
    print("5. Click 'Create GitHub App'")
    print()

def get_github_app_config():
    """Get GitHub App configuration from user"""
    print("📝 STEP 2: Enter Your GitHub App Details")
    print("-" * 40)
    
    name = input("App Name: ").strip()
    if not name:
        print("❌ App name is required!")
        return None
    
    client_id = input("Client ID: ").strip()
    if not client_id:
        print("❌ Client ID is required!")
        return None
    
    client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print("❌ Client Secret is required!")
        return None
    
    return {
        'name': name,
        'client_id': client_id,
        'client_secret': client_secret,
        'app_id': 1,  # Default value
        'redirect_uri': 'http://localhost:8000/github/oauth/callback/'
    }

def save_github_app_config(config):
    """Save GitHub App configuration to database"""
    print("💾 STEP 3: Saving Configuration")
    print("-" * 40)
    
    try:
        # Delete existing config if any
        GitHubApp.objects.all().delete()
        
        # Create new config
        github_app = GitHubApp.objects.create(
            name=config['name'],
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            app_id=config['app_id'],
            redirect_uri=config['redirect_uri']
        )
        
        print("✅ GitHub App configuration saved successfully!")
        print(f"   App Name: {github_app.name}")
        print(f"   Client ID: {github_app.client_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving configuration: {str(e)}")
        return False

def print_next_steps():
    """Print next steps for the user"""
    print()
    print("🎉 SETUP COMPLETE!")
    print("=" * 40)
    print("Your GitHub App is now configured. Next steps:")
    print()
    print("1. Start the Django server:")
    print("   python manage.py runserver")
    print()
    print("2. Open your browser and go to:")
    print("   http://localhost:8000")
    print()
    print("3. Login to GitPulse")
    print()
    print("4. Go to GitHub Setup page:")
    print("   http://localhost:8000/github/setup/")
    print()
    print("5. Click 'Connect to GitHub' to test the OAuth2 flow")
    print()
    print("📚 For more information, see the documentation:")
    print("   https://docs.github.com/en/apps/oauth-apps/building-oauth-apps")

def main():
    """Main function"""
    print_header()
    
    # Check if Django is properly configured
    try:
        from django.conf import settings
        if not settings.configured:
            print("❌ Django settings not configured!")
            return 1
    except Exception as e:
        print(f"❌ Error loading Django settings: {str(e)}")
        return 1
    
    # Print instructions
    print_instructions()
    
    # Get configuration from user
    config = get_github_app_config()
    if not config:
        return 1
    
    # Save configuration
    if not save_github_app_config(config):
        return 1
    
    # Print next steps
    print_next_steps()
    
    return 0

if __name__ == '__main__':
    sys.exit(main()) 