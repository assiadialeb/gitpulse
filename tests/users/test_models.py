import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from users.models import UserProfile, UserDeveloperLink


@pytest.mark.django_db
class TestUserProfile(TestCase):
    """Test UserProfile model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_user_profile_creation(self):
        """Test that UserProfile is automatically created when User is created"""
        # UserProfile should be created automatically via signal
        self.assertTrue(hasattr(self.user, 'userprofile'))
        self.assertIsInstance(self.user.userprofile, UserProfile)
        self.assertEqual(self.user.userprofile.user, self.user)
    
    def test_user_profile_str_representation(self):
        """Test string representation of UserProfile"""
        expected = f"{self.user.username}'s profile"
        self.assertEqual(str(self.user.userprofile), expected)
    
    def test_user_profile_default_values(self):
        """Test default values for UserProfile fields"""
        profile = self.user.userprofile
        self.assertIsNone(profile.github_username)
        self.assertIsNone(profile.github_token)
        self.assertIsNone(profile.github_token_expires_at)
        self.assertIsNone(profile.avatar_url)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)
    
    def test_user_profile_github_fields(self):
        """Test GitHub-related fields"""
        profile = self.user.userprofile
        profile.github_username = 'testgithub'
        profile.github_token = 'ghp_testtoken123'
        profile.github_token_expires_at = timezone.now() + timezone.timedelta(hours=1)
        profile.avatar_url = 'https://github.com/testuser.png'
        profile.save()
        
        # Refresh from database
        profile.refresh_from_db()
        self.assertEqual(profile.github_username, 'testgithub')
        self.assertEqual(profile.github_token, 'ghp_testtoken123')
        self.assertIsNotNone(profile.github_token_expires_at)
        self.assertEqual(profile.avatar_url, 'https://github.com/testuser.png')


@pytest.mark.django_db
class TestUserDeveloperLink(TestCase):
    """Test UserDeveloperLink model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.developer_id = '507f1f77bcf86cd799439011'
    
    def test_user_developer_link_creation(self):
        """Test creating UserDeveloperLink"""
        link = UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        self.assertEqual(link.user, self.user)
        self.assertEqual(link.developer_id, self.developer_id)
        self.assertIsNotNone(link.created_at)
        self.assertIsNotNone(link.updated_at)
    
    def test_user_developer_link_str_representation(self):
        """Test string representation of UserDeveloperLink"""
        link = UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        expected = f"{self.user.username} -> Developer {self.developer_id}"
        self.assertEqual(str(link), expected)
    
    def test_user_developer_link_unique_constraint(self):
        """Test unique constraint on user and developer_id"""
        # Create first link
        UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        # Try to create duplicate - should fail
        with self.assertRaises(Exception):  # Could be IntegrityError or ValidationError
            UserDeveloperLink.objects.create(
                user=self.user,
                developer_id=self.developer_id
            )
    
    def test_user_developer_link_validation_user_already_linked(self):
        """Test validation when user is already linked to another developer"""
        # Create first link
        UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        # Try to create another link for the same user
        another_developer_id = '507f1f77bcf86cd799439012'
        link = UserDeveloperLink(
            user=self.user,
            developer_id=another_developer_id
        )
        
        with self.assertRaises(ValidationError) as cm:
            link.clean()
        
        self.assertIn("This user is already linked to a developer", str(cm.exception))
    
    def test_user_developer_link_validation_developer_already_linked(self):
        """Test validation when developer is already linked to another user"""
        # Create first link
        UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        # Create another user
        another_user = User.objects.create_user(
            username='anotheruser',
            email='another@example.com',
            password='testpass123'
        )
        
        # Try to create link for same developer with different user
        link = UserDeveloperLink(
            user=another_user,
            developer_id=self.developer_id
        )
        
        with self.assertRaises(ValidationError) as cm:
            link.clean()
        
        self.assertIn("This developer is already linked to a user", str(cm.exception))
    
    def test_user_developer_link_update_existing(self):
        """Test that updating existing link doesn't trigger validation errors"""
        link = UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        # Update the link - should not raise validation error
        link.developer_id = '507f1f77bcf86cd799439013'
        link.save()  # Should not raise any exception
        
        link.refresh_from_db()
        self.assertEqual(link.developer_id, '507f1f77bcf86cd799439013')
    
    def test_user_developer_link_related_name(self):
        """Test that related_name works correctly"""
        link = UserDeveloperLink.objects.create(
            user=self.user,
            developer_id=self.developer_id
        )
        
        # Access via related_name
        self.assertEqual(self.user.developer_link, link)
        self.assertEqual(self.user.developer_link.developer_id, self.developer_id)
