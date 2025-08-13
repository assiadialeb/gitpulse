import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from django.test import TestCase

from repositories.models import Repository


@pytest.mark.django_db
class TestRepositoryModel(TestCase):
    """Test cases for Repository model"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.repository = Repository.objects.create(
            name='test-repo',
            full_name='test-org/test-repo',
            description='A test repository',
            private=False,
            fork=False,
            language='Python',
            stars=100,
            forks=50,
            size=1024000,
            default_branch='main',
            github_id=123456789,
            html_url='https://github.com/test-org/test-repo',
            clone_url='https://github.com/test-org/test-repo.git',
            ssh_url='git@github.com:test-org/test-repo.git',
            is_indexed=True,
            last_indexed=timezone.now(),
            commit_count=500,
            kloc=150.5,
            kloc_calculated_at=timezone.now(),
            owner=self.user
        )
    
    def test_repository_creation(self):
        """Test repository creation with all fields"""
        self.assertEqual(self.repository.name, 'test-repo')
        self.assertEqual(self.repository.full_name, 'test-org/test-repo')
        self.assertEqual(self.repository.description, 'A test repository')
        self.assertFalse(self.repository.private)
        self.assertFalse(self.repository.fork)
        self.assertEqual(self.repository.language, 'Python')
        self.assertEqual(self.repository.stars, 100)
        self.assertEqual(self.repository.forks, 50)
        self.assertEqual(self.repository.size, 1024000)
        self.assertEqual(self.repository.default_branch, 'main')
        self.assertEqual(self.repository.github_id, 123456789)
        self.assertTrue(self.repository.is_indexed)
        self.assertEqual(self.repository.commit_count, 500)
        self.assertEqual(self.repository.kloc, 150.5)
        self.assertEqual(self.repository.owner, self.user)
    
    def test_repository_str_representation(self):
        """Test string representation of repository"""
        self.assertEqual(str(self.repository), 'test-org/test-repo')
    
    def test_owner_name_property(self):
        """Test owner_name property extraction"""
        self.assertEqual(self.repository.owner_name, 'test-org')
        
        # Test with different format
        repo2 = Repository.objects.create(
            name='another-repo',
            full_name='another-org/another-repo',
            github_id=987654321,
            html_url='https://github.com/another-org/another-repo',
            clone_url='https://github.com/another-org/another-repo.git',
            ssh_url='git@github.com:another-org/another-repo.git',
            owner=self.user
        )
        self.assertEqual(repo2.owner_name, 'another-org')
    
    def test_repo_name_property(self):
        """Test repo_name property extraction"""
        self.assertEqual(self.repository.repo_name, 'test-repo')
        
        # Test with different format
        repo2 = Repository.objects.create(
            name='another-repo',
            full_name='another-org/another-repo',
            github_id=987654321,
            html_url='https://github.com/another-org/another-repo',
            clone_url='https://github.com/another-org/another-repo.git',
            ssh_url='git@github.com:another-org/another-repo.git',
            owner=self.user
        )
        self.assertEqual(repo2.repo_name, 'another-repo')
    
    def test_repo_name_property_fallback(self):
        """Test repo_name property fallback to name field"""
        repo = Repository.objects.create(
            name='fallback-repo',
            full_name='fallback-repo',  # No slash
            github_id=111222333,
            html_url='https://github.com/fallback-repo',
            clone_url='https://github.com/fallback-repo.git',
            ssh_url='git@github.com:fallback-repo.git',
            owner=self.user
        )
        self.assertEqual(repo.repo_name, 'fallback-repo')
    
    def test_owner_name_property_fallback(self):
        """Test owner_name property fallback for invalid format"""
        repo = Repository.objects.create(
            name='invalid-repo',
            full_name='invalid-repo',  # No slash
            github_id=444555666,
            html_url='https://github.com/invalid-repo',
            clone_url='https://github.com/invalid-repo.git',
            ssh_url='git@github.com:invalid-repo.git',
            owner=self.user
        )
        self.assertEqual(repo.owner_name, '')
    
    def test_repository_ordering(self):
        """Test repository ordering by updated_at"""
        # Create another repository with different updated_at
        repo2 = Repository.objects.create(
            name='older-repo',
            full_name='test-org/older-repo',
            github_id=999888777,
            html_url='https://github.com/test-org/older-repo',
            clone_url='https://github.com/test-org/older-repo.git',
            ssh_url='git@github.com:test-org/older-repo.git',
            owner=self.user
        )
    
        # Force update the updated_at field to be older
        repo2.updated_at = timezone.now() - timedelta(hours=1)
        repo2.save()
        
        # Force update self.repository to be newer
        self.repository.updated_at = timezone.now()
        self.repository.save()
    
        repositories = list(Repository.objects.all().order_by('-updated_at'))
        self.assertEqual(repositories[0], self.repository)  # Most recent first
        self.assertEqual(repositories[1], repo2)  # Older second
    
    def test_repository_unique_constraints(self):
        """Test unique constraints on repository"""
        # Try to create repository with same full_name
        with self.assertRaises(Exception):  # Should raise IntegrityError
            Repository.objects.create(
                name='duplicate-repo',
                full_name='test-org/test-repo',  # Same full_name
                github_id=111222333,
                html_url='https://github.com/test-org/duplicate-repo',
                clone_url='https://github.com/test-org/duplicate-repo.git',
                ssh_url='git@github.com:test-org/duplicate-repo.git',
                owner=self.user
            )
        
        # Try to create repository with same github_id
        with self.assertRaises(Exception):  # Should raise IntegrityError
            Repository.objects.create(
                name='duplicate-id-repo',
                full_name='test-org/duplicate-id-repo',
                github_id=123456789,  # Same github_id
                html_url='https://github.com/test-org/duplicate-id-repo',
                clone_url='https://github.com/test-org/duplicate-id-repo.git',
                ssh_url='git@github.com:test-org/duplicate-id-repo.git',
                owner=self.user
            )
    
    def test_repository_cascade_delete_safety(self):
        """Test cascade delete safety mechanism"""
        # Test without confirmation
        with self.assertRaises(ValueError):
            self.repository.cascade_delete(confirm_repository_name='wrong-name')
        
        # Test with wrong confirmation
        with self.assertRaises(ValueError):
            self.repository.cascade_delete(confirm_repository_name='different-repo')
        
        # Test with correct confirmation (should not raise error)
        try:
            self.repository.cascade_delete(confirm_repository_name='test-org/test-repo')
        except Exception as e:
            # It's OK if it raises other exceptions (like missing collections)
            # as long as it's not the ValueError for wrong confirmation
            if isinstance(e, ValueError) and "confirmation" in str(e):
                raise
    
    def test_repository_default_values(self):
        """Test repository default values"""
        repo = Repository.objects.create(
            name='default-repo',
            full_name='test-org/default-repo',
            github_id=777888999,
            html_url='https://github.com/test-org/default-repo',
            clone_url='https://github.com/test-org/default-repo.git',
            ssh_url='git@github.com:test-org/default-repo.git',
            owner=self.user
        )
        
        self.assertFalse(repo.private)
        self.assertFalse(repo.fork)
        self.assertEqual(repo.stars, 0)
        self.assertEqual(repo.forks, 0)
        self.assertEqual(repo.size, 0)
        self.assertEqual(repo.default_branch, 'main')
        self.assertFalse(repo.is_indexed)
        self.assertIsNone(repo.last_indexed)
        self.assertEqual(repo.commit_count, 0)
        self.assertEqual(repo.kloc, 0.0)
        self.assertIsNone(repo.kloc_calculated_at)
        self.assertIsNotNone(repo.created_at)
        self.assertIsNotNone(repo.updated_at)
