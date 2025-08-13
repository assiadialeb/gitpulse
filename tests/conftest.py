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


@pytest.fixture(autouse=True)
def disable_mongodb():
    """Disable MongoDB connection for tests"""
    if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
        with patch('mongoengine.connect'):
            with patch('mongoengine.disconnect'):
                yield
    else:
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
        'created_at': '2023-01-01T00:00:00Z',
        'updated_at': '2023-01-15T10:30:00Z',
        'pushed_at': '2023-01-15T10:30:00Z',
        'size': 1024,
        'stargazers_count': 10,
        'watchers_count': 5,
        'language': 'Python',
        'has_issues': True,
        'has_projects': False,
        'has_downloads': True,
        'has_wiki': False,
        'has_pages': False,
        'forks_count': 2,
        'archived': False,
        'disabled': False,
        'license': {
            'key': 'mit',
            'name': 'MIT License',
            'url': 'https://api.github.com/licenses/mit'
        },
        'default_branch': 'main',
        'permissions': {
            'admin': True,
            'push': True,
            'pull': True
        }
    }


@pytest.fixture
def sample_user():
    """Sample user data for testing"""
    return {
        'id': 1,
        'username': 'testuser',
        'email': 'test@example.com',
        'first_name': 'Test',
        'last_name': 'User',
        'is_active': True,
        'date_joined': '2023-01-01T00:00:00Z'
    }


@pytest.fixture
def sample_project():
    """Sample project data for testing"""
    return {
        'id': 1,
        'name': 'Test Project',
        'description': 'A test project',
        'created_at': '2023-01-01T00:00:00Z',
        'updated_at': '2023-01-15T10:30:00Z',
        'is_active': True
    }


@pytest.fixture
def mock_github_token_service():
    """Mock GitHub token service"""
    with patch('analytics.github_token_service.GitHubTokenService') as mock_service:
        mock_service.get_token_for_repository_access.return_value = 'ghp_test_token_12345'
        mock_service._get_oauth_app_token.return_value = 'ghp_test_token_12345'
        yield mock_service


@pytest.fixture
def mock_llm_service():
    """Mock LLM service"""
    with patch('analytics.llm_service.LLMService') as mock_service:
        mock_service.classify_commit.return_value = {
            'type': 'feat',
            'confidence': 0.95,
            'explanation': 'This commit adds a new feature'
        }
        yield mock_service


class BaseTestCase(TestCase):
    """Base test case with common setup"""
    
    def setUp(self):
        super().setUp()
        # Disable MongoDB for tests if using SQLite
        if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
            self.patcher = patch('mongoengine.connect')
            self.mock_connect = self.patcher.start()
            self.patcher_disconnect = patch('mongoengine.disconnect')
            self.mock_disconnect = self.patcher_disconnect.start()
    
    def tearDown(self):
        if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
            self.patcher.stop()
            self.patcher_disconnect.stop()
        super().tearDown()
