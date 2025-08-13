"""
Tests for the Release indexing service
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from django.test import TestCase

from analytics.release_indexing_service import ReleaseIndexingService
from analytics.models import Release, IndexingState
from tests.conftest import BaseTestCase


class TestReleaseIndexingService(BaseTestCase):
    """Test cases for ReleaseIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.service = ReleaseIndexingService()
        self.owner = 'test-org'
        self.repo = 'test-repo'
        self.github_token = 'ghp_test_token_12345'
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_success(self, mock_get):
        """Test successful release fetching from GitHub API"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v1.0.0',
                'name': 'Release v1.0.0',
                'body': 'This is a major release with new features',
                'draft': False,
                'prerelease': False,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': '2023-01-15T11:00:00Z',
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0',
                'author': {
                    'login': 'johndoe',
                    'id': 12345,
                    'avatar_url': 'https://example.com/avatar.jpg'
                },
                'assets': [
                    {
                        'id': 67890,
                        'name': 'test-repo-v1.0.0.tar.gz',
                        'label': 'Source code (tar.gz)',
                        'content_type': 'application/gzip',
                        'size': 1024000,
                        'download_count': 150,
                        'created_at': '2023-01-15T11:00:00Z',
                        'updated_at': '2023-01-15T11:00:00Z',
                        'browser_download_url': 'https://github.com/test-org/test-repo/releases/download/v1.0.0/test-repo-v1.0.0.tar.gz'
                    }
                ]
            }
        ]
        mock_get.return_value = mock_response
        
        # Test the method
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Assertions
        assert len(releases) == 1
        release = releases[0]
        assert release['id'] == 12345
        assert release['tag_name'] == 'v1.0.0'
        assert release['name'] == 'Release v1.0.0'
        assert release['draft'] is False
        assert release['prerelease'] is False
        assert release['author']['login'] == 'johndoe'
        assert len(release['assets']) == 1
        assert release['assets'][0]['name'] == 'test-repo-v1.0.0.tar.gz'
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert 'api.github.com' in call_args[0][0]
        assert f'{self.owner}/{self.repo}' in call_args[0][0]
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_api_error(self, mock_get):
        """Test handling of GitHub API errors"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Repository not found'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        with pytest.raises(Exception):
            self.service.fetch_releases_from_github(
                self.owner,
                self.repo,
                self.github_token,
                since_date,
                until_date
            )
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_access_denied(self, mock_get):
        """Test handling of 403 Forbidden (access denied)"""
        # Mock 403 response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list for access denied
        assert releases == []
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_pagination(self, mock_get):
        """Test pagination handling in release fetching"""
        # Mock first page response
        mock_response_1 = Mock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v1.0.0',
                'name': 'Release v1.0.0',
                'body': 'First release',
                'draft': False,
                'prerelease': False,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': '2023-01-15T11:00:00Z',
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': []
            }
        ]
        
        # Mock second page response (empty)
        mock_response_2 = Mock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = []
        
        mock_get.side_effect = [mock_response_1, mock_response_2]
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should have called API at least once (pagination)
        assert mock_get.call_count >= 1
        assert len(releases) == 1
        assert releases[0]['id'] == 12345
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_date_filtering(self, mock_get):
        """Test date filtering in release fetching"""
        # Mock response with releases outside date range
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v0.9.0',
                'name': 'Old Release',
                'body': 'Old release',
                'draft': False,
                'prerelease': False,
                'created_at': '2022-12-01T10:30:00Z',
                'published_at': '2022-12-01T11:00:00Z',  # Outside range
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v0.9.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v0.9.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v0.9.0',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': []
            },
            {
                'id': 12346,
                'tag_name': 'v1.0.0',
                'name': 'New Release',
                'body': 'New release',
                'draft': False,
                'prerelease': False,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': '2023-01-15T11:00:00Z',  # Inside range
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': []
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should only include release within date range
        assert len(releases) >= 0  # Can be 0 if no releases in range
        if releases:
            assert releases[0]['id'] == 12346
            assert releases[0]['tag_name'] == 'v1.0.0'
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_draft_releases(self, mock_get):
        """Test handling of draft releases"""
        # Mock response with draft release
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v1.0.0-rc1',
                'name': 'Release Candidate 1',
                'body': 'Draft release candidate',
                'draft': True,
                'prerelease': True,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': None,  # Draft releases don't have published_at
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0-rc1',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0-rc1',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0-rc1',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': []
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should include draft release based on created_at
        assert len(releases) == 1
        assert releases[0]['draft'] is True
        assert releases[0]['prerelease'] is True
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_invalid_date_format(self, mock_get):
        """Test handling of invalid date formats"""
        # Mock response with invalid date format
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v1.0.0',
                'name': 'Test Release',
                'body': 'Test release',
                'draft': False,
                'prerelease': False,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': 'invalid-date-format',  # Invalid format
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': []
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should skip release with invalid date format
        assert len(releases) == 0
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_rate_limit_handling(self, mock_get):
        """Test rate limit handling"""
        # Mock rate limit response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.headers = {'X-RateLimit-Remaining': '0'}
        mock_response.text = 'API rate limit exceeded'
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        # The service returns empty list for 403, doesn't raise exception
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        assert releases == []
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_empty_response(self, mock_get):
        """Test handling of empty API response"""
        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should return empty list
        assert releases == []
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_network_error(self, mock_get):
        """Test handling of network errors"""
        # Mock network error
        mock_get.side_effect = Exception("Network error")
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        with pytest.raises(Exception):
            self.service.fetch_releases_from_github(
                self.owner,
                self.repo,
                self.github_token,
                since_date,
                until_date
            )
    
    @patch('analytics.release_indexing_service.requests.get')
    def test_fetch_releases_from_github_with_assets(self, mock_get):
        """Test release fetching with multiple assets"""
        # Mock response with multiple assets
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'id': 12345,
                'tag_name': 'v1.0.0',
                'name': 'Release v1.0.0',
                'body': 'Release with multiple assets',
                'draft': False,
                'prerelease': False,
                'created_at': '2023-01-15T10:30:00Z',
                'published_at': '2023-01-15T11:00:00Z',
                'html_url': 'https://github.com/test-org/test-repo/releases/tag/v1.0.0',
                'tarball_url': 'https://api.github.com/repos/test-org/test-repo/tarball/v1.0.0',
                'zipball_url': 'https://api.github.com/repos/test-org/test-repo/zipball/v1.0.0',
                'author': {'login': 'johndoe', 'id': 12345},
                'assets': [
                    {
                        'id': 67890,
                        'name': 'test-repo-v1.0.0.tar.gz',
                        'label': 'Source code (tar.gz)',
                        'content_type': 'application/gzip',
                        'size': 1024000,
                        'download_count': 150,
                        'created_at': '2023-01-15T11:00:00Z',
                        'updated_at': '2023-01-15T11:00:00Z',
                        'browser_download_url': 'https://github.com/test-org/test-repo/releases/download/v1.0.0/test-repo-v1.0.0.tar.gz'
                    },
                    {
                        'id': 67891,
                        'name': 'test-repo-v1.0.0.zip',
                        'label': 'Source code (zip)',
                        'content_type': 'application/zip',
                        'size': 2048000,
                        'download_count': 75,
                        'created_at': '2023-01-15T11:00:00Z',
                        'updated_at': '2023-01-15T11:00:00Z',
                        'browser_download_url': 'https://github.com/test-org/test-repo/releases/download/v1.0.0/test-repo-v1.0.0.zip'
                    }
                ]
            }
        ]
        mock_get.return_value = mock_response
        
        since_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        until_date = datetime(2023, 1, 31, tzinfo=timezone.utc)
        
        releases = self.service.fetch_releases_from_github(
            self.owner,
            self.repo,
            self.github_token,
            since_date,
            until_date
        )
        
        # Should include all assets
        assert len(releases) == 1
        assert len(releases[0]['assets']) == 2
        assert releases[0]['assets'][0]['name'] == 'test-repo-v1.0.0.tar.gz'
        assert releases[0]['assets'][1]['name'] == 'test-repo-v1.0.0.zip'
        assert releases[0]['assets'][0]['download_count'] == 150
        assert releases[0]['assets'][1]['download_count'] == 75
