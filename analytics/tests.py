"""
Tests for analytics functionality
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from django.utils import timezone


from analytics.models import Commit, DeveloperGroup, DeveloperAlias
from analytics.developer_grouping_service import DeveloperGroupingService
from github.models import GitHubToken
from django.contrib.auth import get_user_model

User = get_user_model()


class DeveloperGroupingTestCase(TestCase):
    """Test cases for developer grouping functionality"""
    
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Application model no longer exists, using repository-based approach
        self.application_id = 1  # Dummy ID for tests
        
        # Create test commits with multiple developer identities
        self.create_test_commits()
    
    def create_test_commits(self):
        """Create test commits with multiple developer identities"""
        # Patrick Qian with multiple emails
        Commit.objects.create(
            sha='abc123',
            repository_full_name='test/repo',
            application_id=self.application_id,
            message='Test commit 1',
            author_name='Patrick Qian',
            author_email='patrick.qian@company.com',
            committer_name='Patrick Qian',
            committer_email='patrick.qian@company.com',
            authored_date=datetime.utcnow() - timedelta(days=1),
            committed_date=datetime.utcnow() - timedelta(days=1),
            additions=100,
            deletions=10
        )
        
        Commit.objects.create(
            sha='def456',
            repository_full_name='test/repo',
            application_id=self.application_id,
            message='Test commit 2',
            author_name='patrick.qian',
            author_email='patrick.qian@different.com',
            committer_name='patrick.qian',
            committer_email='patrick.qian@different.com',
            authored_date=datetime.utcnow() - timedelta(days=2),
            committed_date=datetime.utcnow() - timedelta(days=2),
            additions=50,
            deletions=5
        )
        
        # Krishna with multiple identities
        Commit.objects.create(
            sha='ghi789',
            repository_full_name='test/repo',
            application_id=self.application_id,
            message='Test commit 3',
            author_name='Krishna Prasad ADHIKARI',
            author_email='krishna.adhikari@company.com',
            committer_name='Krishna Prasad ADHIKARI',
            committer_email='krishna.adhikari@company.com',
            authored_date=datetime.utcnow() - timedelta(days=3),
            committed_date=datetime.utcnow() - timedelta(days=3),
            additions=200,
            deletions=20
        )
        
        Commit.objects.create(
            sha='jkl012',
            repository_full_name='test/repo',
            application_id=self.application_id,
            message='Test commit 4',
            author_name='krishna',
            author_email='krishna.adhikari@different.com',
            committer_name='krishna',
            committer_email='krishna.adhikari@different.com',
            authored_date=datetime.utcnow() - timedelta(days=4),
            committed_date=datetime.utcnow() - timedelta(days=4),
            additions=75,
            deletions=8
        )
        
        # GitHub ID pattern
        Commit.objects.create(
            sha='mno345',
            repository_full_name='test/repo',
            application_id=self.application_id,
            message='Test commit 5',
            author_name='pbench',
            author_email='52410095+pbench@users.noreply.github.com',
            committer_name='pbench',
            committer_email='52410095+pbench@users.noreply.github.com',
            authored_date=datetime.utcnow() - timedelta(days=5),
            committed_date=datetime.utcnow() - timedelta(days=5),
            additions=150,
            deletions=15
        )
    
    def test_developer_grouping(self):
        """Test that developers are properly grouped"""
        grouping_service = DeveloperGroupingService(self.application_id)
        
        # Run grouping
        results = grouping_service.group_developers()
        
        # Check results
        self.assertGreater(results['total_developers'], 0)
        self.assertGreater(results['groups_created'], 0)
        
        # Get grouped developers
        grouped_devs = grouping_service.get_grouped_developers()
        
        # Should have at least one group with multiple aliases
        multi_alias_groups = [g for g in grouped_devs if len(g['aliases']) > 1]
        self.assertGreater(len(multi_alias_groups), 0)
        
        # Check that Patrick Qian identities are grouped
        patrick_groups = [g for g in grouped_devs if 'patrick' in g['primary_name'].lower()]
        if patrick_groups:
            patrick_group = patrick_groups[0]
            self.assertGreater(len(patrick_group['aliases']), 1)
        
        # Check that Krishna identities are grouped
        krishna_groups = [g for g in grouped_devs if 'krishna' in g['primary_name'].lower()]
        if krishna_groups:
            krishna_group = krishna_groups[0]
            self.assertGreater(len(krishna_group['aliases']), 1)
    
    def test_email_domain_matching(self):
        """Test email domain + username matching"""
        grouping_service = DeveloperGroupingService(self.application.id)
        
        # Test same domain, similar username
        dev1 = {'name': 'test', 'email': 'user1@company.com'}
        dev2 = {'name': 'test', 'email': 'user2@company.com'}
        
        # Should not match (different usernames)
        self.assertFalse(grouping_service._email_domain_username_match(dev1, dev2))
        
        # Test similar usernames
        dev1 = {'name': 'test', 'email': 'patrick.qian@company.com'}
        dev2 = {'name': 'test', 'email': 'patrick_qian@company.com'}
        
        # Should match (similar usernames)
        self.assertTrue(grouping_service._email_domain_username_match(dev1, dev2))
    
    def test_name_similarity_matching(self):
        """Test name similarity matching"""
        grouping_service = DeveloperGroupingService(self.application.id)
        
        # Test similar names
        dev1 = {'name': 'Patrick Qian', 'email': 'test@example.com'}
        dev2 = {'name': 'patrick.qian', 'email': 'test2@example.com'}
        
        # Should match (similar names)
        self.assertTrue(grouping_service._name_similarity_match(dev1, dev2))
        
        # Test different names
        dev1 = {'name': 'Patrick Qian', 'email': 'test@example.com'}
        dev2 = {'name': 'John Doe', 'email': 'test2@example.com'}
        
        # Should not match (different names)
        self.assertFalse(grouping_service._name_similarity_match(dev1, dev2))
    
    def test_github_id_matching(self):
        """Test GitHub ID pattern matching"""
        grouping_service = DeveloperGroupingService(self.application.id)
        
        # Test GitHub ID pattern
        dev1 = {'name': 'user1', 'email': '12345+user1@users.noreply.github.com'}
        dev2 = {'name': 'user2', 'email': '12345+user2@users.noreply.github.com'}
        
        # Should match (same GitHub ID)
        self.assertTrue(grouping_service._github_id_match(dev1, dev2))
        
        # Test different GitHub IDs
        dev1 = {'name': 'user1', 'email': '12345+user1@users.noreply.github.com'}
        dev2 = {'name': 'user2', 'email': '67890+user2@users.noreply.github.com'}
        
        # Should not match (different GitHub IDs)
        self.assertFalse(grouping_service._github_id_match(dev1, dev2)) 


class RateLimitServiceTests(TestCase):
    """Tests for rate limit service functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.github_token = GitHubToken.objects.create(
            user=self.user,
            access_token='test_token',
            token_type='bearer',
            scope='repo',
            expires_at=timezone.now() + timedelta(days=1),
            github_user_id=12345,
            github_username='testuser',
            github_email='test@example.com'
        )
    
    def test_handle_rate_limit_error(self):
        """Test handling rate limit errors"""
        from .services import RateLimitService
        from .github_service import GitHubRateLimitError
        
        error = GitHubRateLimitError("Rate limit exceeded. Retry after 3600 seconds")
        task_data = {
            'application_id': 1,
            'user_id': self.user.id,
            'sync_type': 'full'
        }
        
        result = RateLimitService.handle_rate_limit_error(
            user_id=self.user.id,
            github_username='testuser',
            error=error,
            task_type='sync',
            task_data=task_data
        )
        
        self.assertTrue(result['success'])
        self.assertIn('rate_limit_reset_id', result)
        self.assertIn('reset_time', result)
        self.assertIn('restart_scheduled', result)
    
    def test_parse_reset_time_from_error(self):
        """Test parsing reset time from error message"""
        from .services import RateLimitService
        from .github_service import GitHubRateLimitError
        
        # Test with valid error message
        error = GitHubRateLimitError("Rate limit exceeded. Retry after 3600 seconds")
        reset_time = RateLimitService._parse_reset_time_from_error(error)
        
        # Should be approximately 1 hour from now
        expected_time = timezone.now() + timedelta(seconds=3600)
        self.assertAlmostEqual(
            reset_time.timestamp(),
            expected_time.timestamp(),
            delta=10  # Allow 10 second difference
        )
        
        # Test with invalid error message
        error = GitHubRateLimitError("Rate limit exceeded")
        reset_time = RateLimitService._parse_reset_time_from_error(error)
        
        # Should default to 1 hour from now
        expected_time = timezone.now() + timedelta(hours=1)
        self.assertAlmostEqual(
            reset_time.timestamp(),
            expected_time.timestamp(),
            delta=60  # Allow 1 minute difference for default case
        )
    
    def test_rate_limit_reset_model(self):
        """Test RateLimitReset model"""
        from .models import RateLimitReset
        
        reset = RateLimitReset(
            user_id=self.user.id,
            github_username='testuser',
            rate_limit_reset_time=timezone.now() + timedelta(hours=1),
            pending_task_type='indexing',
            pending_task_data={'application_id': 1, 'user_id': self.user.id},
            status='pending'
        )
        reset.save()
        
        self.assertEqual(reset.user_id, self.user.id)
        self.assertEqual(reset.github_username, 'testuser')
        self.assertEqual(reset.pending_task_type, 'indexing')
        self.assertEqual(reset.status, 'pending')
        
        # Test properties
        self.assertFalse(reset.is_ready_to_restart)
        self.assertGreater(reset.time_until_reset, 0)
        
        # Test when ready to restart
        reset.rate_limit_reset_time = timezone.now() - timedelta(minutes=1)
        reset.save()
        
        self.assertTrue(reset.is_ready_to_restart)
        self.assertEqual(reset.time_until_reset, 0) 