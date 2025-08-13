"""
Pytest configuration and common fixtures for GitPulse tests
"""
import os
import sys
import django
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import TestCase
from django.utils import timezone as django_timezone


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Setup Django database for tests"""
    with django_db_blocker.unblock():
        yield


@pytest.fixture
def mock_github_api():
    """Mock GitHub API responses"""
    with patch('analytics.github_service.requests.get') as mock_get:
        yield mock_get


@pytest.fixture
def mock_ollama_api():
    """Mock Ollama API responses"""
    with patch('analytics.llm_service.requests.post') as mock_post:
        yield mock_post


@pytest.fixture
def sample_commit_data():
    """Sample commit data for testing"""
    return {
        'sha': 'abc123def456',
        'commit': {
            'author': {
                'name': 'John Doe',
                'email': 'john.doe@example.com',
                'date': '2023-01-15T10:30:00Z'
            },
            'committer': {
                'name': 'John Doe',
                'email': 'john.doe@example.com',
                'date': '2023-01-15T10:30:00Z'
            },
            'message': 'feat: add new feature for user authentication'
        },
        'author': {
            'login': 'johndoe',
            'id': 12345,
            'avatar_url': 'https://example.com/avatar.jpg'
        },
        'committer': {
            'login': 'johndoe',
            'id': 12345,
            'avatar_url': 'https://example.com/avatar.jpg'
        },
        'stats': {
            'total': 150,
            'additions': 100,
            'deletions': 50
        },
        'files': [
            {
                'filename': 'src/auth.py',
                'additions': 50,
                'deletions': 10,
                'changes': 60
            },
            {
                'filename': 'tests/test_auth.py',
                'additions': 50,
                'deletions': 40,
                'changes': 90
            }
        ]
    }


@pytest.fixture
def sample_repository():
    """Sample repository data for testing"""
    return {
        'id': 1,
        'full_name': 'test-org/test-repo',
        'name': 'test-repo',
        'description': 'A test repository',
        'private': False,
        'fork': False,
        'language': 'Python',
        'stars': 10,
        'forks': 5,
        'size': 1000,
        'default_branch': 'main',
        'html_url': 'https://github.com/test-org/test-repo',
        'clone_url': 'https://github.com/test-org/test-repo.git',
        'ssh_url': 'git@github.com:test-org/test-repo.git'
    }


@pytest.fixture
def mock_github_token():
    """Mock GitHub token for testing"""
    return 'ghp_test_token_12345'


@pytest.fixture
def sample_commit_list():
    """Sample list of commits for testing"""
    return [
        {
            'sha': 'abc123def456',
            'commit': {
                'author': {
                    'name': 'John Doe',
                    'email': 'john.doe@example.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'committer': {
                    'name': 'John Doe',
                    'email': 'john.doe@example.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'message': 'feat: add new feature for user authentication'
            },
            'stats': {'total': 150, 'additions': 100, 'deletions': 50},
            'files': [{'filename': 'src/auth.py', 'additions': 50, 'deletions': 10}]
        },
        {
            'sha': 'def456ghi789',
            'commit': {
                'author': {
                    'name': 'Jane Smith',
                    'email': 'jane.smith@example.com',
                    'date': '2023-01-14T15:45:00Z'
                },
                'committer': {
                    'name': 'Jane Smith',
                    'email': 'jane.smith@example.com',
                    'date': '2023-01-14T15:45:00Z'
                },
                'message': 'fix: resolve authentication bug'
            },
            'stats': {'total': 25, 'additions': 15, 'deletions': 10},
            'files': [{'filename': 'src/auth.py', 'additions': 15, 'deletions': 10}]
        }
    ]


class BaseTestCase(TestCase):
    """Base test case with common utilities"""
    
    def setUp(self):
        super().setUp()
        self.now = django_timezone.now()
    
    def create_mock_commit(self, **kwargs):
        """Create a mock commit object for testing"""
        from analytics.models import Commit
        
        defaults = {
            'sha': 'test_sha_123',
            'repository_full_name': 'test-org/test-repo',
            'author_name': 'Test Author',
            'author_email': 'test@example.com',
            'message': 'test commit message',
            'authored_date': self.now,
            'committed_date': self.now,
            'additions': 10,
            'deletions': 5,
            'total_changes': 15,
            'commit_type': 'feature'
        }
        defaults.update(kwargs)
        
        return Commit(**defaults)
    
    def create_mock_repository(self, **kwargs):
        """Create a mock repository object for testing"""
        from repositories.models import Repository
        from users.models import User
        
        # Create a mock user if not provided
        if 'owner_id' not in kwargs:
            user, created = User.objects.get_or_create(
                username='testuser',
                defaults={
                    'email': 'test@example.com',
                    'password': 'testpass123'
                }
            )
            kwargs['owner_id'] = user.id
        
        defaults = {
            'name': 'test-repo',
            'full_name': 'test-org/test-repo',
            'description': 'Test repository',
            'private': False,
            'fork': False,
            'language': 'Python',
            'stars': 0,
            'forks': 0,
            'size': 100,
            'default_branch': 'main',
            'github_id': 12345,
            'html_url': 'https://github.com/test-org/test-repo',
            'clone_url': 'https://github.com/test-org/test-repo.git',
            'ssh_url': 'git@github.com:test-org/test-repo.git'
        }
        defaults.update(kwargs)
        
        return Repository(**defaults)
