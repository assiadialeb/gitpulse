import pytest
from unittest.mock import patch, Mock
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from users.services import GitHubUserService
from github.models import GitHubToken


@pytest.mark.django_db
class TestGitHubUserService(TestCase):
    """Test GitHubUserService"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.github_token = GitHubToken.objects.create(
            user=self.user,
            access_token='ghp_testtoken123',
            token_type='bearer',
            scope='repo,user',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
            github_user_id=123,
            github_username='testuser',
            github_email='test@example.com'
        )
    
    def test_service_initialization_with_token(self):
        """Test service initialization with valid token"""
        service = GitHubUserService(self.user.id)
        self.assertEqual(service.user_id, self.user.id)
        self.assertEqual(service.github_token, 'ghp_testtoken123')
    
    def test_service_initialization_without_token(self):
        """Test service initialization without token"""
        # Delete the token
        self.github_token.delete()
        
        with self.assertRaises(ValueError) as cm:
            GitHubUserService(self.user.id)
        
        self.assertIn(f"No GitHub token found for user {self.user.id}", str(cm.exception))
    
    @patch('users.services.requests.get')
    def test_make_request_success(self, mock_get):
        """Test successful API request"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {'id': 123, 'login': 'testuser'}
        mock_response.headers = {'X-RateLimit-Remaining': '4999'}
        mock_get.return_value = mock_response
        
        service = GitHubUserService(self.user.id)
        data, headers = service._make_request('https://api.github.com/users/testuser')
        
        self.assertEqual(data['id'], 123)
        self.assertEqual(data['login'], 'testuser')
        self.assertEqual(headers['X-RateLimit-Remaining'], '4999')
        
        # Verify request was made with correct headers
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]['headers']['Authorization'], 'token ghp_testtoken123')
        self.assertEqual(call_args[1]['headers']['Accept'], 'application/vnd.github.v3+json')
        self.assertEqual(call_args[1]['headers']['User-Agent'], 'GitPulse/1.0')
    
    @patch('users.services.requests.get')
    def test_make_request_404_error(self, mock_get):
        """Test 404 error handling"""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.ok = False
        mock_response.text = 'Not Found'
        mock_get.return_value = mock_response
        
        service = GitHubUserService(self.user.id)
        
        with self.assertRaises(ValueError) as cm:
            service._make_request('https://api.github.com/users/nonexistent')
        
        self.assertIn("GitHub user not found", str(cm.exception))
    
    @patch('users.services.requests.get')
    def test_make_request_api_error(self, mock_get):
        """Test API error handling"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.ok = False
        mock_response.text = 'Forbidden'
        mock_get.return_value = mock_response
        
        service = GitHubUserService(self.user.id)
        
        with self.assertRaises(ValueError) as cm:
            service._make_request('https://api.github.com/users/testuser')
        
        self.assertIn("GitHub API error 403", str(cm.exception))
    
    @patch('users.services.requests.get')
    def test_make_request_network_error(self, mock_get):
        """Test network error handling"""
        # Mock network error - use requests.exceptions.RequestException
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection failed")
        
        service = GitHubUserService(self.user.id)
        
        with self.assertRaises(ValueError) as cm:
            service._make_request('https://api.github.com/users/testuser')
        
        # The service should catch the exception and re-raise as ValueError
        self.assertIn("Request failed", str(cm.exception))
    
    @patch('users.services.requests.get')
    def test_get_user_info_success(self, mock_get):
        """Test successful user info retrieval"""
        # Mock user info response
        mock_user_response = Mock()
        mock_user_response.status_code = 200
        mock_user_response.ok = True
        mock_user_response.json.return_value = {
            'id': 123,
            'login': 'testuser',
            'name': 'Test User',
            'email': 'test@example.com',
            'avatar_url': 'https://github.com/testuser.png',
            'bio': 'Test bio',
            'company': 'Test Company',
            'blog': 'https://testuser.com',
            'location': 'Test City',
            'hireable': True,
            'public_repos': 10,
            'public_gists': 5,
            'followers': 100,
            'following': 50,
            'created_at': '2020-01-01T00:00:00Z',
            'updated_at': '2023-01-01T00:00:00Z'
        }
        mock_user_response.headers = {}
        
        # Mock emails response
        mock_emails_response = Mock()
        mock_emails_response.status_code = 200
        mock_emails_response.ok = True
        mock_emails_response.json.return_value = [
            {'email': 'test@example.com', 'primary': True, 'verified': True},
            {'email': 'test2@example.com', 'primary': False, 'verified': True}
        ]
        mock_emails_response.headers = {}
        
        # Configure mock to return different responses for different URLs
        def mock_get_side_effect(url, **kwargs):
            if 'users/testuser' in url:
                return mock_user_response
            elif 'user/emails' in url:
                return mock_emails_response
            else:
                raise ValueError(f"Unexpected URL: {url}")
        
        mock_get.side_effect = mock_get_side_effect
        
        service = GitHubUserService(self.user.id)
        user_data = service.get_user_info('testuser')
        
        # Verify user data
        self.assertEqual(user_data['github_id'], 123)
        self.assertEqual(user_data['login'], 'testuser')
        self.assertEqual(user_data['name'], 'Test User')
        self.assertEqual(user_data['email'], 'test@example.com')
        self.assertEqual(user_data['avatar_url'], 'https://github.com/testuser.png')
        self.assertEqual(user_data['bio'], 'Test bio')
        self.assertEqual(user_data['company'], 'Test Company')
        self.assertEqual(user_data['blog'], 'https://testuser.com')
        self.assertEqual(user_data['location'], 'Test City')
        self.assertTrue(user_data['hireable'])
        self.assertEqual(user_data['public_repos'], 10)
        self.assertEqual(user_data['public_gists'], 5)
        self.assertEqual(user_data['followers'], 100)
        self.assertEqual(user_data['following'], 50)
        self.assertEqual(user_data['github_created_at'], '2020-01-01T00:00:00Z')
        self.assertEqual(user_data['github_updated_at'], '2023-01-01T00:00:00Z')
        self.assertEqual(len(user_data['emails']), 2)
        self.assertEqual(user_data['emails'][0]['email'], 'test@example.com')
        self.assertTrue(user_data['emails'][0]['primary'])
    
    @patch('users.services.requests.get')
    def test_get_user_info_api_error(self, mock_get):
        """Test user info retrieval with API error"""
        # Mock API error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.ok = False
        mock_response.text = 'Internal Server Error'
        mock_get.return_value = mock_response
        
        service = GitHubUserService(self.user.id)
        
        with self.assertRaises(ValueError) as cm:
            service.get_user_info('testuser')
        
        self.assertIn("GitHub API error 500", str(cm.exception))
    
    @patch('users.services.requests.get')
    def test_get_user_info_network_error(self, mock_get):
        """Test user info retrieval with network error"""
        # Mock network error - use requests.exceptions.RequestException
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection timeout")
        
        service = GitHubUserService(self.user.id)
        
        with self.assertRaises(ValueError) as cm:
            service.get_user_info('testuser')
        
        # The service should catch the exception and re-raise as ValueError
        self.assertIn("Request failed", str(cm.exception))
    
    def test_service_with_nonexistent_user(self):
        """Test service with non-existent user"""
        with self.assertRaises(ValueError) as cm:
            GitHubUserService(99999)  # Non-existent user ID
        
        self.assertIn("No GitHub token found for user 99999", str(cm.exception))
