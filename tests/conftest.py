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
def mock_mongodb():
    """Mock MongoDB for all tests"""
    if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
        # Mock mongoengine connection
        with patch('mongoengine.connect'), patch('mongoengine.disconnect'):
            yield
    else:
        yield


@pytest.fixture(autouse=True)
def mock_mongodb_objects():
    """Mock MongoDB objects for testing"""
    if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
        # Create a simple mock queryset
        mock_qs = Mock()
        mock_qs.first.return_value = None
        mock_qs.count.return_value = 0
        mock_qs.order_by.return_value = mock_qs
        mock_qs.all.return_value = []
        mock_qs.filter.return_value = mock_qs
        mock_qs.get.return_value = None
        
        # Mock all MongoDB objects with the same mock queryset
        with patch('analytics.models.Commit.objects') as mock_commit_objects, \
             patch('analytics.models.PullRequest.objects') as mock_pr_objects, \
             patch('analytics.models.Release.objects') as mock_release_objects, \
             patch('analytics.models.SBOM.objects') as mock_sbom_objects, \
             patch('analytics.models.CodeQLVulnerability.objects') as mock_codeql_objects, \
             patch('analytics.models.IndexingState.objects') as mock_indexing_objects:
            
            # Apply the same mock queryset to all objects
            for mock_objects in [mock_commit_objects, mock_pr_objects, mock_release_objects, 
                               mock_sbom_objects, mock_codeql_objects, mock_indexing_objects]:
                mock_objects.filter.return_value = mock_qs
                mock_objects.first.return_value = None
                mock_objects.count.return_value = 0
                mock_objects.all.return_value = []
                mock_objects.get.return_value = None
            
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


@pytest.fixture
def mock_commit_objects():
    """Mock Commit.objects for testing"""
    with patch('analytics.models.Commit.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.order_by.return_value = []
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


@pytest.fixture
def mock_pullrequest_objects():
    """Mock PullRequest.objects for testing"""
    with patch('analytics.models.PullRequest.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


@pytest.fixture
def mock_release_objects():
    """Mock Release.objects for testing"""
    with patch('analytics.models.Release.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


@pytest.fixture
def mock_sbom_objects():
    """Mock SBOM.objects for testing"""
    with patch('analytics.models.SBOM.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


@pytest.fixture
def mock_codeql_objects():
    """Mock CodeQLVulnerability.objects for testing"""
    with patch('analytics.models.CodeQLVulnerability.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.order_by.return_value = []
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


@pytest.fixture
def mock_indexing_state_objects():
    """Mock IndexingState.objects for testing"""
    with patch('analytics.models.IndexingState.objects') as mock_objects:
        mock_queryset = Mock()
        mock_objects.filter.return_value = mock_queryset
        mock_objects.filter.return_value.first.return_value = None
        mock_objects.filter.return_value.count.return_value = 0
        mock_objects.filter.return_value.all.return_value = []
        yield mock_objects


class BaseTestCase(TestCase):
    """Base test case with common setup"""
    
    def setUp(self):
        super().setUp()
        # MongoDB is already mocked by fixtures
    
    def tearDown(self):
        super().tearDown()
