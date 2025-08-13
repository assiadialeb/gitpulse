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
    """Mock MongoDB for all tests (CI-safe: no real Mongo connection)."""
    # Always prevent real connections in tests
    with patch('mongoengine.connect'), patch('mongoengine.disconnect'), patch('mongoengine.get_connection'):
        yield


@pytest.fixture(autouse=True)
def setup_django_db(django_db_setup, django_db_blocker):
    """Setup Django database and ensure tables exist"""
    with django_db_blocker.unblock():
        from django.core.management import call_command
        try:
            call_command('migrate', verbosity=0)
        except Exception:
            # If migrations fail, try to create basic tables
            from django.db import connection
            with connection.cursor() as cursor:
                # Create auth_user table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth_user (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        password VARCHAR(128) NOT NULL,
                        last_login DATETIME NULL,
                        is_superuser BOOLEAN NOT NULL,
                        username VARCHAR(150) UNIQUE NOT NULL,
                        first_name VARCHAR(150) NOT NULL,
                        last_name VARCHAR(150) NOT NULL,
                        email VARCHAR(254) NOT NULL,
                        is_staff BOOLEAN NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        date_joined DATETIME NOT NULL
                    )
                """)
                
                # Create repositories_repository table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS repositories_repository (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(255) NOT NULL,
                        full_name VARCHAR(255) UNIQUE NOT NULL,
                        description TEXT NULL,
                        private BOOLEAN NOT NULL,
                        fork BOOLEAN NOT NULL,
                        language VARCHAR(50) NULL,
                        stars INTEGER NOT NULL,
                        forks INTEGER NOT NULL,
                        size BIGINT NOT NULL,
                        default_branch VARCHAR(100) NOT NULL,
                        github_id BIGINT UNIQUE NOT NULL,
                        html_url VARCHAR(200) NOT NULL,
                        clone_url VARCHAR(200) NOT NULL,
                        ssh_url VARCHAR(200) NOT NULL,
                        is_indexed BOOLEAN NOT NULL,
                        last_indexed DATETIME NULL,
                        commit_count INTEGER NOT NULL,
                        kloc REAL NOT NULL,
                        kloc_calculated_at DATETIME NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        owner_id INTEGER NOT NULL
                    )
                """)
        yield


@pytest.fixture(autouse=True)
def mock_mongodb_objects():
    """Mock MongoDB objects for testing (prevent any real Mongo access)."""
    # Create a simple mock queryset
    mock_qs = Mock()
    mock_qs.first.return_value = None
    mock_qs.count.return_value = 0
    mock_qs.order_by.return_value = mock_qs
    mock_qs.all.return_value = []
    mock_qs.filter.return_value = mock_qs
    mock_qs.get.return_value = None
    # Make the mock iterable
    mock_qs.__iter__ = lambda self: iter([])
    mock_qs.__len__ = lambda self: 0

    # Mock all MongoDB objects with the same mock queryset
    with patch('analytics.models.Commit.objects') as mock_commit_objects, \
         patch('analytics.models.PullRequest.objects') as mock_pr_objects, \
         patch('analytics.models.Release.objects') as mock_release_objects, \
         patch('analytics.models.SBOM.objects') as mock_sbom_objects, \
         patch('analytics.models.CodeQLVulnerability.objects') as mock_codeql_objects, \
         patch('analytics.models.IndexingState.objects') as mock_indexing_objects, \
         patch('analytics.models.Developer.objects') as mock_developer_objects, \
         patch('analytics.models.DeveloperAlias.objects') as mock_developer_alias_objects, \
         patch('analytics.models.SonarCloudMetrics.objects') as mock_sonar_metrics_objects, \
         patch('analytics.models.RepositoryStats.objects') as mock_repo_stats_objects, \
         patch('analytics.models.SyncLog.objects') as mock_sync_log_objects, \
         patch('analytics.models.RepositoryKLOCHistory.objects') as mock_kloc_history_objects, \
         patch('analytics.models.SecurityHealthHistory.objects') as mock_sh_history_objects, \
         patch('analytics.models.Deployment.objects') as mock_deployment_objects:

        # Apply the same mock queryset to all objects
        for mock_objects in [
            mock_commit_objects,
            mock_pr_objects,
            mock_release_objects,
            mock_sbom_objects,
            mock_codeql_objects,
            mock_indexing_objects,
            mock_developer_objects,
            mock_developer_alias_objects,
            mock_sonar_metrics_objects,
            mock_repo_stats_objects,
            mock_sync_log_objects,
            mock_kloc_history_objects,
            mock_sh_history_objects,
            mock_deployment_objects,
        ]:
            mock_objects.filter.return_value = mock_qs
            mock_objects.first.return_value = None
            mock_objects.count.return_value = 0
            mock_objects.all.return_value = []
            mock_objects.get.return_value = None
            # Add model attribute with __name__ for UnifiedMetricsService
            mock_objects.model = Mock()
            mock_objects.model.__name__ = 'MockModel'
            # Also configure the filter return value to have the same model
            mock_objects.filter.return_value.model = mock_objects.model

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
def mock_repository():
    """Mock repository for testing"""
    mock_repo = Mock()
    mock_repo.id = 1
    mock_repo.full_name = 'test-org/test-repo'
    mock_repo.name = 'test-repo'
    mock_repo.owner = 'test-org'
    mock_repo.description = 'A test repository'
    mock_repo.private = False
    mock_repo.fork = False
    mock_repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    mock_repo.updated_at = datetime(2023, 1, 15, tzinfo=timezone.utc)
    mock_repo.save.return_value = None
    return mock_repo


@pytest.fixture
def mock_commit():
    """Mock commit for testing"""
    mock_commit = Mock()
    mock_commit.sha = 'abc123def456'
    mock_commit.repository_full_name = 'test-org/test-repo'
    mock_commit.author_name = 'John Doe'
    mock_commit.author_email = 'john.doe@example.com'
    mock_commit.committer_name = 'John Doe'
    mock_commit.committer_email = 'john.doe@example.com'
    mock_commit.message = 'feat: add new feature'
    mock_commit.additions = 100
    mock_commit.deletions = 50
    mock_commit.total_changes = 150
    mock_commit.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    mock_commit.save.return_value = None
    return mock_commit


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
    """Base test case with common setup (for backward compatibility)"""
    
    def setUp(self):
        super().setUp()
        # MongoDB is already mocked by fixtures
    
    def tearDown(self):
        super().tearDown()
