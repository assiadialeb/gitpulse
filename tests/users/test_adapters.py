import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from users.adapters import CustomSocialAccountAdapter


class TestCustomSocialAccountAdapter(TestCase):
    """Test cases for CustomSocialAccountAdapter"""

    def setUp(self):
        """Set up test fixtures"""
        self.adapter = CustomSocialAccountAdapter()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create a mock social login
        self.social_login = Mock()
        self.social_login.account = Mock()
        self.social_login.account.provider = 'github'
        self.social_login.account.user = self.user
        
        # Create a mock token
        self.mock_token = Mock()
        self.mock_token.token = 'test_github_token_123'
        self.social_login.token = self.mock_token
        
        # Create request
        self.request = self.factory.get('/')
        self.request.session = {}

    def test_adapter_inheritance(self):
        """Test that CustomSocialAccountAdapter inherits from DefaultSocialAccountAdapter"""
        self.assertIsInstance(self.adapter, DefaultSocialAccountAdapter)

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    @patch('users.adapters.SocialToken.objects.get_or_create')
    def test_pre_social_login_github_success(self, mock_get_or_create, mock_social_app_filter, mock_logger):
        """Test successful GitHub token capture during social login"""
        # Mock SocialApp
        mock_social_app = Mock()
        mock_social_app_filter.return_value.first.return_value = mock_social_app
        
        # Mock SocialToken creation
        mock_social_token = Mock()
        mock_get_or_create.return_value = (mock_social_token, True)  # created=True
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify SocialApp was queried
        mock_social_app_filter.assert_called_once_with(provider='github')
        
        # Verify SocialToken was created
        mock_get_or_create.assert_called_once_with(
            account=self.social_login.account,
            app=mock_social_app,
            defaults={'token': 'test_github_token_123'}
        )
        
        # Verify token was stored in session
        self.assertEqual(self.request.session['github_token'], 'test_github_token_123')
        
        # Verify logging
        mock_logger.info.assert_any_call(f"Capturing GitHub token for user {self.user.username}")
        mock_logger.info.assert_any_call(f"GitHub token captured and stored for user {self.user.username}")

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    @patch('users.adapters.SocialToken.objects.get_or_create')
    def test_pre_social_login_github_existing_token(self, mock_get_or_create, mock_social_app_filter, mock_logger):
        """Test GitHub token update when token already exists"""
        # Mock SocialApp
        mock_social_app = Mock()
        mock_social_app_filter.return_value.first.return_value = mock_social_app
        
        # Mock existing SocialToken
        mock_social_token = Mock()
        mock_get_or_create.return_value = (mock_social_token, False)  # created=False
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify token was updated
        self.assertEqual(mock_social_token.token, 'test_github_token_123')
        mock_social_token.save.assert_called_once()

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    def test_pre_social_login_no_social_app(self, mock_social_app_filter, mock_logger):
        """Test behavior when no SocialApp is found"""
        # Mock no SocialApp found
        mock_social_app_filter.return_value.first.return_value = None
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify no token was stored in session
        self.assertNotIn('github_token', self.request.session)
        
        # Verify no error was logged
        mock_logger.error.assert_not_called()

    @patch('users.adapters.logger')
    def test_pre_social_login_no_token(self, mock_logger):
        """Test behavior when no token is available"""
        # Remove token from social login
        self.social_login.token = None
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify no token was stored in session
        self.assertNotIn('github_token', self.request.session)
        
        # Verify no error was logged
        mock_logger.error.assert_not_called()

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    def test_pre_social_login_non_github_provider(self, mock_social_app_filter, mock_logger):
        """Test behavior with non-GitHub provider"""
        # Change provider to something else
        self.social_login.account.provider = 'google'
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify no SocialApp was queried
        mock_social_app_filter.assert_not_called()
        
        # Verify no token was stored in session
        self.assertNotIn('github_token', self.request.session)

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    @patch('users.adapters.SocialToken.objects.get_or_create')
    def test_pre_social_login_exception_handling(self, mock_get_or_create, mock_social_app_filter, mock_logger):
        """Test exception handling during token capture"""
        # Mock SocialApp
        mock_social_app = Mock()
        mock_social_app_filter.return_value.first.return_value = mock_social_app
        
        # Mock exception during token creation
        mock_get_or_create.side_effect = Exception("Database error")
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify error was logged
        mock_logger.error.assert_called_once_with("Error capturing GitHub token: Database error")
        
        # Verify no token was stored in session
        self.assertNotIn('github_token', self.request.session)

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    @patch('users.adapters.SocialToken.objects.get_or_create')
    def test_pre_social_login_no_hasattr_token(self, mock_get_or_create, mock_social_app_filter, mock_logger):
        """Test behavior when social login has no token attribute"""
        # Remove token attribute completely
        delattr(self.social_login, 'token')
        
        # Call the method
        self.adapter.pre_social_login(self.request, self.social_login)
        
        # Verify no SocialApp was queried
        mock_social_app_filter.assert_not_called()
        
        # Verify no token was stored in session
        self.assertNotIn('github_token', self.request.session)

    @patch('users.adapters.logger')
    @patch('users.adapters.SocialApp.objects.filter')
    @patch('users.adapters.SocialToken.objects.get_or_create')
    def test_pre_social_login_calls_parent_method(self, mock_get_or_create, mock_social_app_filter, mock_logger):
        """Test that parent method is called"""
        # Mock SocialApp
        mock_social_app = Mock()
        mock_social_app_filter.return_value.first.return_value = mock_social_app
        
        # Mock SocialToken creation
        mock_social_token = Mock()
        mock_get_or_create.return_value = (mock_social_token, True)
        
        # Mock parent method
        with patch.object(DefaultSocialAccountAdapter, 'pre_social_login') as mock_parent:
            self.adapter.pre_social_login(self.request, self.social_login)
            
            # Verify parent method was called
            mock_parent.assert_called_once_with(self.request, self.social_login)
