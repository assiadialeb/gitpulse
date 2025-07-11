#!/usr/bin/env python
"""
Simple test script to verify our analytics system structure
"""
import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def test_imports():
    """Test that all our modules can be imported correctly"""
    print("Testing imports...")
    
    try:
        from analytics.models import Commit, SyncLog, RepositoryStats
        print("✓ Analytics models imported successfully")
    except Exception as e:
        print(f"✗ Failed to import analytics models: {e}")
        return False
    
    try:
        from analytics.github_service import GitHubService, GitHubAPIError
        print("✓ GitHub service imported successfully")
    except Exception as e:
        print(f"✗ Failed to import GitHub service: {e}")
        return False
    
    try:
        from analytics.sync_service import SyncService
        print("✓ Sync service imported successfully")
    except Exception as e:
        print(f"✗ Failed to import sync service: {e}")
        return False
    
    try:
        from analytics.tasks import sync_application_task, manual_sync_application
        print("✓ Analytics tasks imported successfully")
    except Exception as e:
        print(f"✗ Failed to import analytics tasks: {e}")
        return False
    
    return True

def test_github_service():
    """Test GitHub service with fake token"""
    print("\nTesting GitHub service...")
    
    try:
        from analytics.github_service import GitHubService
        
        # Create service with fake token (just to test structure)
        service = GitHubService("fake_token")
        print("✓ GitHub service created successfully")
        
        # Test parsing method (without making actual API calls)
        fake_commit_data = {
            'sha': 'abc123',
            'commit': {
                'message': 'Test commit',
                'author': {
                    'name': 'Test Author',
                    'email': 'test@example.com',
                    'date': '2025-01-01T12:00:00Z'
                },
                'committer': {
                    'name': 'Test Committer', 
                    'email': 'committer@example.com',
                    'date': '2025-01-01T12:00:00Z'
                }
            },
            'stats': {
                'additions': 10,
                'deletions': 5,
                'total': 15
            },
            'files': [],
            'parents': [],
            'html_url': 'https://github.com/test/repo/commit/abc123'
        }
        
        parsed = service.parse_commit_data(fake_commit_data, "test/repo", 1)
        print("✓ Commit data parsing works")
        print(f"  Parsed SHA: {parsed['sha']}")
        print(f"  Parsed message: {parsed['message']}")
        
        return True
        
    except Exception as e:
        print(f"✗ GitHub service test failed: {e}")
        return False

def test_model_structure():
    """Test model structure without database operations"""
    print("\nTesting model structure...")
    
    try:
        from analytics.models import Commit, FileChange
        from datetime import datetime
        
        # Test creating model instances (without saving)
        commit = Commit(
            sha='test123',
            repository_full_name='test/repo',
            application_id=1,
            message='Test commit',
            author_name='Test Author',
            author_email='test@example.com',
            committer_name='Test Committer',
            committer_email='committer@example.com',
            authored_date=datetime.utcnow(),
            committed_date=datetime.utcnow()
        )
        
        print("✓ Commit model structure is valid")
        print(f"  SHA: {commit.sha}")
        print(f"  Message: {commit.message}")
        
        return True
        
    except Exception as e:
        print(f"✗ Model structure test failed: {e}")
        return False

def test_django_q_imports():
    """Test Django-Q imports"""
    print("\nTesting Django-Q imports...")
    
    try:
        from django_q.tasks import async_task
        from django_q.models import Task, Schedule
        print("✓ Django-Q imported successfully")
        return True
    except Exception as e:
        print(f"✗ Django-Q import failed: {e}")
        return False

def main():
    """Run all tests"""
    print("GitPulse Analytics System Test")
    print("=" * 40)
    
    all_passed = True
    
    # Test imports
    if not test_imports():
        all_passed = False
    
    # Test GitHub service
    if not test_github_service():
        all_passed = False
    
    # Test model structure
    if not test_model_structure():
        all_passed = False
    
    # Test Django-Q
    if not test_django_q_imports():
        all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("✓ All tests passed! System structure is ready.")
        print("\nNext steps:")
        print("1. Install and start MongoDB")
        print("2. Start Redis server")
        print("3. Run: python manage.py test_sync --application-id=1")
        print("4. Start Django-Q cluster: python manage.py qcluster")
    else:
        print("✗ Some tests failed. Check errors above.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 