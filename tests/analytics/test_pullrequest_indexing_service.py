"""
Tests for the Pull Request indexing service
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from django.test import TestCase

from analytics.pullrequest_indexing_service import PullRequestIndexingService
from analytics.models import PullRequest, IndexingState
from tests.conftest import BaseTestCase


class TestPullRequestIndexingService(BaseTestCase):
    """Test cases for PullRequestIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.service = PullRequestIndexingService()
        self.owner = 'test-org'
        self.repo = 'test-repo'
        self.github_token = 'ghp_test_token_12345'
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_success(self, mock_get):
        """Test successful pull request fetching from GitHub API"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'number': 123,
                'title': 'Add new feature',
                'state': 'closed',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'closed_at': '2023-01-16T15:45:00Z',
                'merged_at': '2023-01-16T15:45:00Z',
                'html_url': 'https://github.com/test-org/test-repo/pull/123',
                'user': {
                    'login': 'johndoe',
                    'id': 12345
                },
                'merged_by': {
                    'login': 'janedoe',
                    'id': 67890
                },
                'head': {
                    'ref': 'feature-branch',
                    'sha': 'abc123def456'
                },
                'base': {
                    'ref': 'main',
                    'sha': 'def456ghi789'
                },
                'additions': 150,
                'deletions': 50,
                'changed_files': 5,
                'comments': 10,
                'review_comments': 5,
                'commits': 3,
                'labels': [
                    {'name': 'enhancement', 'color': 'a2eeef'}
                ],
                'assignees': [
                    {'login': 'johndoe', 'id': 12345}
                ],
                'requested_reviewers': [
                    {'login': 'janedoe', 'id': 67890}
                ]
            }
        ]
        mock_get.return_value = mock_response
        
        # Test the method
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Assertions
        assert len(pull_requests) == 1
        pr = pull_requests[0]
        assert pr['number'] == 123
        assert pr['title'] == 'Add new feature'
        assert pr['state'] == 'closed'
        assert pr['author'] == 'johndoe'
        assert pr['merged_by'] == 'janedoe'
        assert pr['additions'] == 150
        assert pr['deletions'] == 50
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'api.github.com' in call_args[0][0]
        assert f'{self.owner}/{self.repo}' in call_args[0][0]
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_api_error(self, mock_get):
        """Test handling of GitHub API errors"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Repository not found'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        with pytest.raises(Exception):
            self.service.fetch_pullrequests_from_github(
                self.owner,
                self.repo,
                self.github_token,
                since_date,
                until_date
            )
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_access_denied(self, mock_get):
        """Test handling of 403 Forbidden (access denied)"""
        # Mock 403 response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list for access denied
        assert pull_requests == []
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_pagination(self, mock_get):
        """Test pagination handling in pull request fetching"""
        # Mock first page response
        mock_response_1 = Mock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = [
            {
                'number': 123,
                'title': 'First PR',
                'state': 'closed',
                'created_at': '2023-01-15T10:30:00Z',
                'updated_at': '2023-01-16T15:45:00Z',
                'closed_at': '2023-01-16T15:45:00Z',
                'merged_at': '2023-01-16T15:45:00Z',
                'html_url': 'https://github.com/test-org/test-repo/pull/123',
                'user': {'login': 'johndoe', 'id': 12345},
                'merged_by': {'login': 'janedoe', 'id': 67890},
                'head': {'ref': 'feature-branch', 'sha': 'abc123def456'},
                'base': {'ref': 'main', 'sha': 'def456ghi789'},
                'additions': 150,
                'deletions': 50,
                'changed_files': 5,
                'comments': 10,
                'review_comments': 5,
                'commits': 3,
                'labels': [],
                'assignees': [],
                'requested_reviewers': []
            }
        ]
        
        # Mock second page response (empty)
        mock_response_2 = Mock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = []
        
        mock_get.side_effect = [mock_response_1, mock_response_2]
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should have called API twice (pagination)
        assert mock_get.call_count == 2
        assert len(pull_requests) == 1
        assert pull_requests[0]['number'] == 123
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_date_filtering(self, mock_get):
        """Test date filtering in pull request fetching"""
        # Mock response with PRs outside date range
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'number': 123,
                'title': 'Old PR',
                'state': 'closed',
                'created_at': '2022-12-01T10:30:00Z',  # Outside range
                'updated_at': '2022-12-02T15:45:00Z',
                'closed_at': '2022-12-02T15:45:00Z',
                'merged_at': '2022-12-02T15:45:00Z',
                'html_url': 'https://github.com/test-org/test-repo/pull/123',
                'user': {'login': 'johndoe', 'id': 12345},
                'merged_by': {'login': 'janedoe', 'id': 67890},
                'head': {'ref': 'feature-branch', 'sha': 'abc123def456'},
                'base': {'ref': 'main', 'sha': 'def456ghi789'},
                'additions': 150,
                'deletions': 50,
                'changed_files': 5,
                'comments': 10,
                'review_comments': 5,
                'commits': 3,
                'labels': [],
                'assignees': [],
                'requested_reviewers': []
            },
            {
                'number': 124,
                'title': 'New PR',
                'state': 'closed',
                'created_at': '2023-01-15T10:30:00Z',  # Inside range
                'updated_at': '2023-01-16T15:45:00Z',
                'closed_at': '2023-01-16T15:45:00Z',
                'merged_at': '2023-01-16T15:45:00Z',
                'html_url': 'https://github.com/test-org/test-repo/pull/124',
                'user': {'login': 'johndoe', 'id': 12345},
                'merged_by': {'login': 'janedoe', 'id': 67890},
                'head': {'ref': 'feature-branch', 'sha': 'abc123def456'},
                'base': {'ref': 'main', 'sha': 'def456ghi789'},
                'additions': 100,
                'deletions': 25,
                'changed_files': 3,
                'comments': 5,
                'review_comments': 2,
                'commits': 2,
                'labels': [],
                'assignees': [],
                'requested_reviewers': []
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should only include PR within date range
        assert len(pull_requests) == 1
        assert pull_requests[0]['number'] == 124
        assert pull_requests[0]['title'] == 'New PR'
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_invalid_date_format(self, mock_get):
        """Test handling of invalid date formats"""
        # Mock response with invalid date format
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'number': 123,
                'title': 'Test PR',
                'state': 'closed',
                'created_at': 'invalid-date-format',  # Invalid format
                'updated_at': '2023-01-16T15:45:00Z',
                'closed_at': '2023-01-16T15:45:00Z',
                'merged_at': '2023-01-16T15:45:00Z',
                'html_url': 'https://github.com/test-org/test-repo/pull/123',
                'user': {'login': 'johndoe', 'id': 12345},
                'merged_by': {'login': 'janedoe', 'id': 67890},
                'head': {'ref': 'feature-branch', 'sha': 'abc123def456'},
                'base': {'ref': 'main', 'sha': 'def456ghi789'},
                'additions': 150,
                'deletions': 50,
                'changed_files': 5,
                'comments': 10,
                'review_comments': 5,
                'commits': 3,
                'labels': [],
                'assignees': [],
                'requested_reviewers': []
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should skip PR with invalid date format
        assert len(pull_requests) == 0
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_rate_limit_handling(self, mock_get):
        """Test rate limit handling"""
        # Mock rate limit response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '0'}
        mock_response.text = 'API rate limit exceeded'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        with pytest.raises(Exception):
            self.service.fetch_pullrequests_from_github(
                self.owner,
                self.repo,
                self.github_token,
                since_date,
                until_date
            )
    
    def test_fetch_pullrequests_from_github_missing_required_fields(self):
        """Test handling of missing required fields in PR data"""
        # This test would verify that the service handles missing fields gracefully
        # Implementation would depend on how the service handles missing data
        pass
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_empty_response(self, mock_get):
        """Test handling of empty API response"""
        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        pull_requests = self.service.fetch_pullrequests_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list
        assert pull_requests == []
    
    @patch('analytics.pullrequest_indexing_service.requests.get')
    def test_fetch_pullrequests_from_github_network_error(self, mock_get):
        """Test handling of network errors"""
        # Mock network error
        mock_get.side_effect = Exception("Network error")
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        with pytest.raises(Exception):
            self.service.fetch_pullrequests_from_github(
                self.owner,
                self.repo,
                self.github_token,
                since_date,
                until_date
            )
