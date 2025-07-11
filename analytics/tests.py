"""
Tests for analytics functionality
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta

from applications.models import Application
from analytics.models import Commit, DeveloperGroup, DeveloperAlias
from analytics.developer_grouping_service import DeveloperGroupingService


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
        
        # Create test application
        self.application = Application.objects.create(
            name='Test App',
            description='Test application for developer grouping',
            owner=self.user
        )
        
        # Create test commits with multiple developer identities
        self.create_test_commits()
    
    def create_test_commits(self):
        """Create test commits with multiple developer identities"""
        # Patrick Qian with multiple emails
        Commit.objects.create(
            sha='abc123',
            repository_full_name='test/repo',
            application_id=self.application.id,
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
            application_id=self.application.id,
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
            application_id=self.application.id,
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
            application_id=self.application.id,
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
            application_id=self.application.id,
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
        grouping_service = DeveloperGroupingService(self.application.id)
        
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