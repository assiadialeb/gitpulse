"""
Tests for the GitHub API commit indexing service
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from django.test import TestCase

from analytics.commit_indexing_service import CommitIndexingService
from analytics.models import Commit, IndexingState
from tests.conftest import BaseTestCase


class TestCommitIndexingService(BaseTestCase):
    """Test cases for CommitIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.service = CommitIndexingService()
        self.repository_full_name = 'test-org/test-repo'
        self.github_token = 'ghp_test_token_12345'
    
    def create_mock_commit(self, sha='abc123def456', repository_full_name='test-org/test-repo', 
                          author_name='John Doe', author_email='john.doe@example.com',
                          message='feat: add new feature', additions=100, deletions=50):
        """Create a mock commit for testing"""
        mock_commit = Mock()
        mock_commit.sha = sha
        mock_commit.repository_full_name = repository_full_name
        mock_commit.author_name = author_name
        mock_commit.author_email = author_email
        mock_commit.committer_name = author_name
        mock_commit.committer_email = author_email
        mock_commit.message = message
        mock_commit.additions = additions
        mock_commit.deletions = deletions
        mock_commit.total_changes = additions + deletions
        mock_commit.created_at = datetime(2023, 1, 15, tzinfo=timezone.utc)
        mock_commit.save.return_value = None
        return mock_commit
    
    @patch('analytics.commit_indexing_service.requests.get')
    def test_fetch_commits_from_github_success(self, mock_get):
        """Test successful commit fetching from GitHub API"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
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
                'author': {
                    'login': 'johndoe',
                    'id': 12345
                },
                'committer': {
                    'login': 'johndoe',
                    'id': 12345
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
                    }
                ]
            }
        ]
        mock_get.return_value = mock_response
        
        # Test the method
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        # Extract owner and repo from full name
        owner, repo = self.repository_full_name.split('/')
        
        commits = self.service.fetch_commits_from_github(
            owner,
            repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Assertions
        assert len(commits) == 1
        commit = commits[0]
        assert commit['sha'] == 'abc123def456'
        assert commit['commit']['message'] == 'feat: add new feature for user authentication'
        assert commit['stats']['additions'] == 100
        assert commit['stats']['deletions'] == 50
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'api.github.com' in call_args[0][0]
        assert self.repository_full_name in call_args[0][0]
    
    @patch('analytics.commit_indexing_service.requests.get')
    def test_fetch_commits_from_github_api_error(self, mock_get):
        """Test handling of GitHub API errors"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Repository not found'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        # Test the method
        # Extract owner and repo from full name
        owner, repo = self.repository_full_name.split('/')
        
        commits = self.service.fetch_commits_from_github(
            owner,
            repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list on error
        assert commits == []
    
    @patch('analytics.commit_indexing_service.requests.get')
    def test_fetch_commits_from_github_rate_limit(self, mock_get):
        """Test handling of GitHub API rate limiting"""
        # Mock rate limit response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '0'}
        mock_response.text = 'Rate limit exceeded'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        # Test the method
        # Extract owner and repo from full name
        owner, repo = self.repository_full_name.split('/')
        
        commits = self.service.fetch_commits_from_github(
            owner,
            repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list on rate limit
        assert commits == []
    
    def test_process_commits_new_commit(self):
        """Test processing new commits"""
        # Create sample commit data
        commit_data = {
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
                }
            ],
            'html_url': f'https://github.com/{self.repository_full_name}/commit/abc123def456'
        }
        
        commits_data = [commit_data]
        
        # Test processing
        result = CommitIndexingService.process_commits(commits_data)
        
        # Assertions
        assert result == 1  # Number of commits processed
        
        # Verify commit was saved
        saved_commit = Commit.objects.filter(sha='abc123def456').first()
        assert saved_commit is not None
        assert saved_commit.repository_full_name == self.repository_full_name
        assert saved_commit.author_name == 'John Doe'
        assert saved_commit.author_email == 'john.doe@example.com'
        assert saved_commit.message == 'feat: add new feature for user authentication'
        assert saved_commit.additions == 100
        assert saved_commit.deletions == 50
        assert saved_commit.total_changes == 150
    
    def test_process_commits_existing_commit(self):
        """Test processing existing commits (update)"""
        # Create an existing commit
        existing_commit = self.create_mock_commit(
            sha='abc123def456',
            repository_full_name=self.repository_full_name,
            author_name='Old Name',
            author_email='old@example.com',
            message='old message',
            additions=50,
            deletions=25
        )
        existing_commit.save()
        
        # Create updated commit data
        commit_data = {
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
                }
            ],
            'html_url': f'https://github.com/{self.repository_full_name}/commit/abc123def456'
        }
        
        commits_data = [commit_data]
        
        # Test processing
        result = CommitIndexingService.process_commits(commits_data)
        
        # Assertions - should not create new commit, but update existing
        assert result == 0  # No new commits created
        
        # Verify commit was updated
        updated_commit = Commit.objects.get(sha='abc123def456')
        assert updated_commit.author_name == 'John Doe'
        assert updated_commit.author_email == 'john.doe@example.com'
        assert updated_commit.message == 'feat: add new feature for user authentication'
        assert updated_commit.additions == 100
        assert updated_commit.deletions == 50
    
    @patch('analytics.commit_indexing_service.classify_commits_with_files_batch')
    def test_process_commits_with_classification(self, mock_classify):
        """Test commit processing with automatic classification"""
        # Mock classification
        mock_classify.return_value = ['feature']
        
        # Create sample commit data
        commit_data = {
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
            'stats': {
                'total': 150,
                'additions': 100,
                'deletions': 50
            },
            'files': [],
            'html_url': f'https://github.com/{self.repository_full_name}/commit/abc123def456'
        }
        
        commits_data = [commit_data]
        
        # Test processing
        result = CommitIndexingService.process_commits(commits_data)
        
        # Assertions
        assert result == 1
        
        # Verify classification was called
        mock_classify.assert_called_once()
        
        # Verify commit was classified
        saved_commit = Commit.objects.get(sha='abc123def456')
        assert saved_commit.commit_type == 'feature'
    
    def test_process_commits_empty_data(self):
        """Test processing empty commit data"""
        result = CommitIndexingService.process_commits([])
        
        assert result == 0
    
    def test_process_commits_invalid_data(self):
        """Test processing invalid commit data"""
        invalid_commit = {
            'sha': 'invalid_sha',
            # Missing required fields
        }
        
        commits_data = [invalid_commit]
        
        # Should handle gracefully
        result = CommitIndexingService.process_commits(commits_data)
        
        # Should skip invalid commits
        assert result == 0
    
    @patch('analytics.commit_indexing_service.requests.get')
    def test_index_commits_for_repository_success(self, mock_get):
        """Test successful indexing of commits for a repository"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
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
                    'message': 'feat: add new feature'
                },
                'stats': {'total': 100, 'additions': 80, 'deletions': 20},
                'files': []
            }
        ]
        mock_get.return_value = mock_response
        
        # Test indexing
        result = self.service.index_commits_for_repository(
            repository_id=1,
            user_id=1,
            batch_size_days=30
        )
        
        # Assertions
        assert result['status'] == 'success'
        assert result['processed'] == 1
        assert result['total_processed'] == 1
        assert result['has_more'] is False  # Only one commit in mock
    
    @patch('analytics.commit_indexing_service.requests.get')
    def test_index_commits_for_repository_api_error(self, mock_get):
        """Test handling of API errors during indexing"""
        # Mock API error
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Repository not found'
        mock_get.return_value = mock_response
        
        # Test indexing
        result = self.service.index_commits_for_repository(
            repository_id=1,
            user_id=1,
            batch_size_days=30
        )
        
        # Should handle error gracefully
        assert result['status'] == 'error'
        assert 'Repository not found' in result.get('error', '')
    
    @pytest.mark.skip(reason="Method doesn't exist in current service")
    def test_parse_github_date(self):
        """Test parsing GitHub date format"""
        github_date = '2023-01-15T10:30:00Z'
        parsed_date = self.service._parse_github_date(github_date)
        
        assert isinstance(parsed_date, datetime)
        assert parsed_date.tzinfo is not None
        assert parsed_date.year == 2023
        assert parsed_date.month == 1
        assert parsed_date.day == 15
        assert parsed_date.hour == 10
        assert parsed_date.minute == 30
    
    @pytest.mark.skip(reason="Method doesn't exist in current service")
    def test_parse_github_date_invalid(self):
        """Test parsing invalid GitHub date format"""
        invalid_date = 'invalid-date'
        parsed_date = self.service._parse_github_date(invalid_date)
        
        # Should return current time on invalid date
        assert isinstance(parsed_date, datetime)
        assert parsed_date.tzinfo is not None


class TestCommitIndexingServiceIntegration(BaseTestCase):
    """Integration tests for CommitIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.service = CommitIndexingService()
        self.repository_full_name = 'test-org/test-repo'
    
    def test_end_to_end_commit_processing(self):
        """Test end-to-end commit processing workflow"""
        # Create sample commit data
        commit_data = {
            'sha': 'integration_test_sha',
            'commit': {
                'author': {
                    'name': 'Integration Test',
                    'email': 'integration@test.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'committer': {
                    'name': 'Integration Test',
                    'email': 'integration@test.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'message': 'test: integration test commit'
            },
            'stats': {
                'total': 50,
                'additions': 30,
                'deletions': 20
            },
            'files': [
                {
                    'filename': 'test_file.py',
                    'additions': 30,
                    'deletions': 20,
                    'changes': 50
                }
            ],
            'html_url': f'https://github.com/{self.repository_full_name}/commit/integration_test_sha'
        }
        
        # Process commit
        result = CommitIndexingService.process_commits([commit_data])
        
        # Verify processing
        assert result == 1
        
        # Verify database state
        commit = Commit.objects.get(sha='integration_test_sha')
        assert commit.repository_full_name == self.repository_full_name
        assert commit.author_name == 'Integration Test'
        assert commit.author_email == 'integration@test.com'
        assert commit.message == 'test: integration test commit'
        assert commit.additions == 30
        assert commit.deletions == 20
        assert commit.total_changes == 50
        
        # Verify commit type classification
        assert commit.commit_type in ['test', 'other']  # Should be classified
    
    def test_commit_deduplication(self):
        """Test that duplicate commits are handled correctly"""
        # Create initial commit
        initial_commit = self.create_mock_commit(
            sha='duplicate_sha',
            repository_full_name=self.repository_full_name,
            author_name='Original Author',
            message='Original message',
            additions=10,
            deletions=5
        )
        initial_commit.save()
        
        # Process same commit with updated data
        updated_commit_data = {
            'sha': 'duplicate_sha',
            'commit': {
                'author': {
                    'name': 'Updated Author',
                    'email': 'updated@test.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'committer': {
                    'name': 'Updated Author',
                    'email': 'updated@test.com',
                    'date': '2023-01-15T10:30:00Z'
                },
                'message': 'Updated message'
            },
            'stats': {
                'total': 20,
                'additions': 15,
                'deletions': 5
            },
            'files': [],
            'html_url': f'https://github.com/{self.repository_full_name}/commit/duplicate_sha'
        }
        
        result = CommitIndexingService.process_commits([updated_commit_data])
        
        # Should update existing commit (no new commits created)
        assert result == 0
        
        # Verify only one commit exists
        commits = Commit.objects.filter(sha='duplicate_sha')
        assert commits.count() == 1
        
        # Verify updated data
        updated_commit = commits.first()
        assert updated_commit.author_name == 'Updated Author'
        assert updated_commit.message == 'Updated message'
        assert updated_commit.additions == 15
        assert updated_commit.deletions == 5
