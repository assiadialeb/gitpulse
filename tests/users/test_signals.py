import pytest
from django.test import TestCase
from django.contrib.auth.models import User
from users.models import UserProfile


@pytest.mark.django_db
class TestUserSignals(TestCase):
    """Test user signals"""
    
    def test_create_user_profile_signal(self):
        """Test that UserProfile is created when User is created"""
        # Create a new user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Check that UserProfile was created automatically
        self.assertTrue(hasattr(user, 'userprofile'))
        self.assertIsInstance(user.userprofile, UserProfile)
        self.assertEqual(user.userprofile.user, user)
        
        # Check that UserProfile exists in database
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.user, user)
    
    def test_save_user_profile_signal(self):
        """Test that UserProfile is saved when User is saved"""
        # Create a user (UserProfile should be created automatically)
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Modify the user
        user.first_name = 'Updated'
        user.save()
        
        # Check that UserProfile still exists and is linked
        user.refresh_from_db()
        self.assertTrue(hasattr(user, 'userprofile'))
        self.assertIsInstance(user.userprofile, UserProfile)
    
    def test_user_profile_creation_with_existing_user(self):
        """Test UserProfile creation for existing user without profile"""
        # Create user without triggering signals
        user = User.objects.create(
            username='testuser',
            email='test@example.com'
        )
        user.set_password('testpass123')
        user.save()
        
        # Check if UserProfile was already created by signal
        if hasattr(user, 'userprofile'):
            profile = user.userprofile
        else:
            # Manually create UserProfile
            profile = UserProfile.objects.create(user=user)
        
        # Check that profile is properly linked
        self.assertEqual(profile.user, user)
        self.assertTrue(hasattr(user, 'userprofile'))
        self.assertEqual(user.userprofile, profile)
    
    def test_multiple_user_creation(self):
        """Test that multiple users get their own profiles"""
        # Create multiple users
        user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        # Check that each user has their own profile
        self.assertTrue(hasattr(user1, 'userprofile'))
        self.assertTrue(hasattr(user2, 'userprofile'))
        self.assertNotEqual(user1.userprofile, user2.userprofile)
        
        # Check profiles in database
        profiles = UserProfile.objects.all()
        self.assertEqual(profiles.count(), 2)
        self.assertIn(user1.userprofile, profiles)
        self.assertIn(user2.userprofile, profiles)
    
    def test_user_profile_default_values(self):
        """Test that UserProfile has correct default values"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        profile = user.userprofile
        
        # Check default values
        self.assertIsNone(profile.github_username)
        self.assertIsNone(profile.github_token)
        self.assertIsNone(profile.github_token_expires_at)
        self.assertIsNone(profile.avatar_url)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)
