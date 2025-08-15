import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from repositories.models import Repository
from repositories.views import _get_dora_metrics

User = get_user_model()


class DORAMetricsTestCase(TestCase):
    """Test cases for DORA metrics calculation using mocks"""
    
    def _setup_pr_mock(self, mock_pr, return_prs):
        """Helper to setup PR mock with chained filter calls"""
        mock_pr_query = Mock()
        mock_pr_query.filter.return_value = mock_pr_query  # Return self for chaining
        mock_pr_query.__iter__ = lambda self: iter(return_prs)  # Make it iterable
        mock_pr.objects.filter.return_value = mock_pr_query
    
    def _setup_deployment_mock(self, mock_deployment, return_deployments):
        """Helper to setup Deployment mock with chained filter calls"""
        mock_deployment_query = Mock()
        mock_deployment_query.filter.return_value = mock_deployment_query  # Return self for chaining
        mock_deployment_query.__iter__ = lambda self: iter(return_deployments)  # Make it iterable
        mock_deployment.objects.filter.return_value = mock_deployment_query
    
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test repository
        self.repository = Repository.objects.create(
            name='test-repo-dora',
            full_name='test-org/test-repo-dora',
            description='Test repository for DORA metrics',
            private=False,
            language='Python',
            stars=100,
            forks=50,
            size=1000,
            default_branch='main',
            github_id=12345,
            html_url='https://github.com/test-org/test-repo-dora',
            clone_url='https://github.com/test-org/test-repo-dora.git',
            ssh_url='git@github.com:test-org/test-repo-dora.git',
            is_indexed=True,
            commit_count=500,
            owner=self.user
        )
        
        # Mock data for testing
        self.mock_deployment1 = Mock()
        self.mock_deployment1.deployment_id = '1'
        self.mock_deployment1.environment = 'production'
        self.mock_deployment1.created_at = datetime.now() - timedelta(days=20)
        self.mock_deployment1.updated_at = datetime.now() - timedelta(days=20)
        self.mock_deployment1.statuses = [
            {
                'state': 'success',
                'created_at': (datetime.now() - timedelta(days=20)).isoformat(),
                'updated_at': (datetime.now() - timedelta(days=20)).isoformat()
            }
        ]
        
        self.mock_deployment2 = Mock()
        self.mock_deployment2.deployment_id = '2'
        self.mock_deployment2.environment = 'production'
        self.mock_deployment2.created_at = datetime.now() - timedelta(days=5)
        self.mock_deployment2.updated_at = datetime.now() - timedelta(days=5)
        self.mock_deployment2.statuses = [
            {
                'state': 'success',
                'created_at': (datetime.now() - timedelta(days=5)).isoformat(),
                'updated_at': (datetime.now() - timedelta(days=5)).isoformat()
            }
        ]
        
        self.mock_commit1 = Mock()
        self.mock_commit1.sha = 'abc123def4567890abcdef1234567890abcdef12'
        self.mock_commit1.authored_date = datetime.now() - timedelta(days=30)
        
        self.mock_commit2 = Mock()
        self.mock_commit2.sha = 'def456ghi7890123456789abcdef0123456789ab'
        self.mock_commit2.authored_date = datetime.now() - timedelta(days=15)
        
        self.mock_pr = Mock()
        self.mock_pr.number = 1
        self.mock_pr.title = 'Test PR'
        self.mock_pr.state = 'closed'
        self.mock_pr.merged_at = datetime.now() - timedelta(days=10)
        self.mock_pr.commit_shas = ['abc123def4567890abcdef1234567890abcdef12', 'def456ghi7890123456789abcdef0123456789ab']
    
    def tearDown(self):
        """Clean up test data"""
        # Clean up Django models
        if hasattr(self, 'repository'):
            self.repository.delete()
        if hasattr(self, 'user'):
            self.user.delete()
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_basic(self, mock_commit, mock_pr, mock_deployment):
        """Test basic DORA metrics calculation with mocks"""
        # Setup mocks
        self._setup_deployment_mock(mock_deployment, [self.mock_deployment1, self.mock_deployment2])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [self.mock_pr])
        
        # Mock Commit query
        mock_commit.objects.filter.return_value = [self.mock_commit1, self.mock_commit2]
        
        metrics = _get_dora_metrics(self.repository)
        
        # Check structure
        self.assertIn('deployment_frequency', metrics)
        self.assertIn('lead_time', metrics)
        
        # Check deployment frequency
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 2)
        self.assertEqual(metrics['deployment_frequency']['period_days'], 180)
        self.assertAlmostEqual(metrics['deployment_frequency']['deployments_per_day'], 0.011, places=3)
        
        # Check deployment frequency performance
        self.assertIn('performance', metrics['deployment_frequency'])
        self.assertIn('grade', metrics['deployment_frequency']['performance'])
        self.assertIn('color', metrics['deployment_frequency']['performance'])
        
        # Check lead time structure
        self.assertIn('lt1_median_hours', metrics['lead_time'])
        self.assertIn('lt1_mean_hours', metrics['lead_time'])
        self.assertIn('lt2_median_hours', metrics['lead_time'])
        self.assertIn('lt2_mean_hours', metrics['lead_time'])
        self.assertIn('lt1_median_days', metrics['lead_time'])
        self.assertIn('lt1_mean_days', metrics['lead_time'])
        self.assertIn('lt2_median_days', metrics['lead_time'])
        self.assertIn('lt2_mean_days', metrics['lead_time'])
        self.assertIn('lt1_performance', metrics['lead_time'])
        self.assertIn('lt2_performance', metrics['lead_time'])
        self.assertIn('total_prs_analyzed', metrics['lead_time'])
        
        # Check performance structure
        self.assertIn('grade', metrics['lead_time']['lt1_performance'])
        self.assertIn('color', metrics['lead_time']['lt1_performance'])
        self.assertIn('grade', metrics['lead_time']['lt2_performance'])
        self.assertIn('color', metrics['lead_time']['lt2_performance'])
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_no_deployments(self, mock_commit, mock_pr, mock_deployment):
        """Test DORA metrics when no deployments exist"""
        # Setup mocks - no deployments
        self._setup_deployment_mock(mock_deployment, [])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [])
        
        mock_commit.objects.filter.return_value = []
        
        metrics = _get_dora_metrics(self.repository)
        
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 0)
        self.assertEqual(metrics['deployment_frequency']['deployments_per_day'], 0)
        self.assertIsNone(metrics['lead_time']['lt1_median_hours'])
        self.assertIsNone(metrics['lead_time']['lt2_median_hours'])
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_no_prs(self, mock_commit, mock_pr, mock_deployment):
        """Test DORA metrics when no pull requests exist"""
        # Setup mocks - deployments but no PRs
        self._setup_deployment_mock(mock_deployment, [self.mock_deployment1, self.mock_deployment2])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [])
        
        mock_commit.objects.filter.return_value = []
        
        metrics = _get_dora_metrics(self.repository)
        
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 2)
        self.assertEqual(metrics['lead_time']['total_prs_analyzed'], 0)
        self.assertIsNone(metrics['lead_time']['lt1_median_hours'])
        self.assertIsNone(metrics['lead_time']['lt2_median_hours'])
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_production_environment_detection(self, mock_commit, mock_pr, mock_deployment):
        """Test that different production environments are detected"""
        # Create mock deployments with different production environment names
        test_environments = ['prod', 'live', 'main', 'master', 'github-pages']
        mock_deployments = []
        
        for i, env in enumerate(test_environments):
            mock_deploy = Mock()
            mock_deploy.deployment_id = str(10 + i)
            mock_deploy.environment = env
            mock_deploy.created_at = datetime.now() - timedelta(days=i)
            mock_deploy.updated_at = datetime.now() - timedelta(days=i)
            mock_deploy.statuses = [
                {
                    'state': 'success',
                    'created_at': (datetime.now() - timedelta(days=i)).isoformat(),
                    'updated_at': (datetime.now() - timedelta(days=i)).isoformat()
                }
            ]
            mock_deployments.append(mock_deploy)
        
        # Add original deployments
        mock_deployments.extend([self.mock_deployment1, self.mock_deployment2])
        
        # Setup mocks
        self._setup_deployment_mock(mock_deployment, mock_deployments)
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [])
        
        mock_commit.objects.filter.return_value = []
        
        metrics = _get_dora_metrics(self.repository)
        
        # Should detect all production deployments (original 2 + 5 new ones)
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 7)
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_non_production_environment(self, mock_commit, mock_pr, mock_deployment):
        """Test that non-production environments are ignored"""
        # Create mock deployment with non-production environment
        mock_staging_deploy = Mock()
        mock_staging_deploy.deployment_id = '100'
        mock_staging_deploy.environment = 'staging'
        mock_staging_deploy.created_at = datetime.now() - timedelta(days=1)
        mock_staging_deploy.updated_at = datetime.now() - timedelta(days=1)
        mock_staging_deploy.statuses = [
            {
                'state': 'success',
                'created_at': (datetime.now() - timedelta(days=1)).isoformat(),
                'updated_at': (datetime.now() - timedelta(days=1)).isoformat()
            }
        ]
        
        # Setup mocks - include staging deployment
        self._setup_deployment_mock(mock_deployment, [self.mock_deployment1, self.mock_deployment2, mock_staging_deploy])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [])
        
        mock_commit.objects.filter.return_value = []
        
        metrics = _get_dora_metrics(self.repository)
        
        # Should only count production deployments (original 2)
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 2)
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_deployment_without_success_status(self, mock_commit, mock_pr, mock_deployment):
        """Test that deployments without success status are ignored"""
        # Create mock deployment without success status
        mock_pending_deploy = Mock()
        mock_pending_deploy.deployment_id = '200'
        mock_pending_deploy.environment = 'production'
        mock_pending_deploy.created_at = datetime.now() - timedelta(days=1)
        mock_pending_deploy.updated_at = datetime.now() - timedelta(days=1)
        mock_pending_deploy.statuses = [
            {
                'state': 'pending',
                'created_at': (datetime.now() - timedelta(days=1)).isoformat(),
                'updated_at': (datetime.now() - timedelta(days=1)).isoformat()
            }
        ]
        
        # Setup mocks - include pending deployment
        self._setup_deployment_mock(mock_deployment, [self.mock_deployment1, self.mock_deployment2, mock_pending_deploy])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [])
        
        mock_commit.objects.filter.return_value = []
        
        metrics = _get_dora_metrics(self.repository)
        
        # Should only count successful production deployments (original 2)
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 2)
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_lead_time_calculation(self, mock_commit, mock_pr, mock_deployment):
        """Test that lead time calculations are reasonable"""
        # Setup mocks
        self._setup_deployment_mock(mock_deployment, [self.mock_deployment1, self.mock_deployment2])
        
        # Setup PR mock
        self._setup_pr_mock(mock_pr, [self.mock_pr])
        
        # Mock Commit query
        mock_commit.objects.filter.return_value = [self.mock_commit1, self.mock_commit2]
        
        metrics = _get_dora_metrics(self.repository)
        
        # Check that lead times are calculated
        if metrics['lead_time']['lt1_median_hours'] is not None:
            self.assertGreater(metrics['lead_time']['lt1_median_hours'], 0)
            self.assertGreater(metrics['lead_time']['lt1_median_days'], 0)
        
        if metrics['lead_time']['lt2_median_hours'] is not None:
            self.assertGreater(metrics['lead_time']['lt2_median_hours'], 0)
            self.assertGreater(metrics['lead_time']['lt2_median_days'], 0)
        
        # Check that days are calculated correctly (hours / 24)
        if metrics['lead_time']['lt1_median_hours'] is not None:
            expected_days = metrics['lead_time']['lt1_median_hours'] / 24
            self.assertAlmostEqual(metrics['lead_time']['lt1_median_days'], expected_days, places=2)
        
        if metrics['lead_time']['lt2_median_hours'] is not None:
            expected_days = metrics['lead_time']['lt2_median_hours'] / 24
            self.assertAlmostEqual(metrics['lead_time']['lt2_median_days'], expected_days, places=2)
    
    @patch('analytics.models.Deployment')
    @patch('analytics.models.PullRequest')
    @patch('analytics.models.Commit')
    def test_get_dora_metrics_error_handling(self, mock_commit, mock_pr, mock_deployment):
        """Test error handling in DORA metrics calculation"""
        # Setup mocks to raise exception
        mock_deployment.objects.filter.side_effect = Exception("Database error")
        
        # Test with invalid repository (should not raise exception)
        invalid_repo = Repository(
            name='invalid',
            full_name='invalid/invalid',
            private=False
        )
        
        metrics = _get_dora_metrics(invalid_repo)
        
        # Should return default structure
        self.assertIn('deployment_frequency', metrics)
        self.assertIn('lead_time', metrics)
        self.assertEqual(metrics['deployment_frequency']['total_deployments'], 0)
        self.assertEqual(metrics['lead_time']['total_prs_analyzed'], 0)
        
        # Check performance fields exist even on error
        self.assertIn('performance', metrics['deployment_frequency'])
        self.assertIn('lt1_performance', metrics['lead_time'])
        self.assertIn('lt2_performance', metrics['lead_time'])

    def test_classify_dora_performance(self):
        """Test DORA performance classification function"""
        from repositories.views import _classify_dora_performance
        
        # Test deployment frequency classification
        self.assertEqual(_classify_dora_performance('deployment_frequency', 2.0)['grade'], 'Elite')
        self.assertEqual(_classify_dora_performance('deployment_frequency', 0.5)['grade'], 'High')
        self.assertEqual(_classify_dora_performance('deployment_frequency', 0.1)['grade'], 'Medium')
        self.assertEqual(_classify_dora_performance('deployment_frequency', 0.01)['grade'], 'Low')
        
        # Test LT1 classification
        self.assertEqual(_classify_dora_performance('lt1', 0.01)['grade'], 'Elite')
        self.assertEqual(_classify_dora_performance('lt1', 0.5)['grade'], 'High')
        self.assertEqual(_classify_dora_performance('lt1', 3.0)['grade'], 'Medium')
        self.assertEqual(_classify_dora_performance('lt1', 10.0)['grade'], 'Low')
        
        # Test LT2 classification
        self.assertEqual(_classify_dora_performance('lt2', 0.01)['grade'], 'Elite')
        self.assertEqual(_classify_dora_performance('lt2', 0.2)['grade'], 'High')
        self.assertEqual(_classify_dora_performance('lt2', 1.0)['grade'], 'Medium')
        self.assertEqual(_classify_dora_performance('lt2', 3.0)['grade'], 'Low')
        
        # Test edge cases
        self.assertEqual(_classify_dora_performance('deployment_frequency', 0)['grade'], 'N/A')
        self.assertEqual(_classify_dora_performance('deployment_frequency', None)['grade'], 'N/A')
