"""
Tests for the intelligent indexing service
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from django.test import TestCase

from analytics.intelligent_indexing_service import IntelligentIndexingService
from analytics.models import IndexingState
from tests.conftest import BaseTestCase


class TestIntelligentIndexingService(BaseTestCase):
    """Test cases for IntelligentIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.repository_full_name = 'test-org/test-repo'
        self.entity_type = 'commits'
        self.github_token = 'ghp_test_token_12345'
        self.now = datetime.now(timezone.utc)
        
        # Create a mock repository for testing
        self.repository = self.create_mock_repository(
            full_name=self.repository_full_name
        )
        self.repository.save()
        
        self.service = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
    
    def create_mock_repository(self, full_name='test-org/test-repo'):
        """Create a mock repository for testing"""
        mock_repo = Mock()
        mock_repo.id = 1
        mock_repo.full_name = full_name
        mock_repo.name = full_name.split('/')[-1]
        mock_repo.owner = full_name.split('/')[0]
        mock_repo.description = 'A test repository'
        mock_repo.private = False
        mock_repo.fork = False
        mock_repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_repo.updated_at = datetime(2023, 1, 15, tzinfo=timezone.utc)
        mock_repo.save.return_value = None
        return mock_repo
    
    def test_initialization(self):
        """Test service initialization"""
        assert self.service.repository_id == self.repository.id
        assert self.service.entity_type == self.entity_type
        assert self.service.github_token == self.github_token
        assert self.service.repository.full_name == self.repository_full_name
        assert self.service.state is not None
    
    def test_get_adaptive_batch_size_new_repository(self):
        """Test adaptive batch size for new repository"""
        # New repository (no indexing history)
        self.service.state.total_indexed = 0
        self.service.state.last_indexed_at = None
        
        batch_size = self.service.get_adaptive_batch_size()
        
        # Should use larger batch size for new repositories
        assert batch_size >= 30
    
    def test_get_adaptive_batch_size_small_repository(self):
        """Test adaptive batch size for small repository"""
        # Small repository (< 100 items)
        self.service.state.total_indexed = 50
        self.service.state.last_indexed_at = self.now - timedelta(days=1)
        
        batch_size = self.service.get_adaptive_batch_size()
        
        # Should use medium batch size
        assert batch_size >= 15
    
    def test_get_adaptive_batch_size_large_repository(self):
        """Test adaptive batch size for large repository"""
        # Large repository (> 1000 items)
        self.service.state.total_indexed = 1500
        self.service.state.last_indexed_at = self.now - timedelta(days=1)
        
        batch_size = self.service.get_adaptive_batch_size()
        
        # Should use smaller batch size
        assert batch_size == 7
    
    def test_get_date_range_for_next_batch(self):
        """Test date range calculation for next batch"""
        # Set up state
        self.service.state.last_indexed_at = datetime(2023, 1, 15, tzinfo=timezone.utc)
        self.service.state.total_indexed = 100
        
        since_date, until_date = self.service.get_date_range_for_next_batch(batch_size_days=30)
        
        # Verify date range
        assert since_date == datetime(2023, 1, 15, tzinfo=timezone.utc)
        expected_until = datetime(2023, 1, 15, tzinfo=timezone.utc) + timedelta(days=30)
        assert until_date == expected_until
    
    def test_get_date_range_for_next_batch_no_history(self):
        """Test date range calculation for repository with no history"""
        # No previous indexing
        self.service.state.last_indexed_at = None
        self.service.state.total_indexed = 0
        
        since_date, until_date = self.service.get_date_range_for_next_batch(batch_size_days=30)
        
        # Should start from a reasonable past date
        assert since_date < self.now
        assert until_date > since_date
        assert (until_date - since_date).days == 30
    
    def test_has_more_to_index_with_more_data(self):
        """Test has_more_to_index when more data is available"""
        since_date = self.now - timedelta(days=10)
        
        has_more = self.service.has_more_to_index(since_date)
        
        # Should return True for recent dates
        assert has_more is True
    
    def test_has_more_to_index_old_data(self):
        """Test has_more_to_index for very old data"""
        # Very old date (more than 10 years)
        since_date = self.now - timedelta(days=3650)
        
        has_more = self.service.has_more_to_index(since_date)
        
        # Should return False for very old dates
        assert has_more is False
    
    @patch('analytics.intelligent_indexing_service.requests.get')
    def test_index_batch_success(self, mock_get):
        """Test successful batch indexing"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'sha': 'abc123def456',
                'commit': {
                    'author': {
                        'name': 'John Doe',
                        'email': 'john.doe@example.com',
                        'date': '2023-01-15T10:30:00Z'
                    },
                    'committer': {
                        'name': 'John Doe',
                        'email': 'john.doe@example.com',
                        'date': '2023-01-15T10:30:00Z'
                    },
                    'message': 'feat: add new feature'
                },
                'stats': {'total': 100, 'additions': 80, 'deletions': 20},
                'files': []
            }
        ]
        mock_get.return_value = mock_response
        
        # Mock process function
        def mock_process_function(data):
            return len(data)
        
        # Test batch indexing
        result = self.service.index_batch(
            fetch_function=lambda *args: mock_response.json(),
            process_function=mock_process_function,
            batch_size_days=30
        )
        
        # Verify result
        assert result['status'] == 'success'
        assert result['processed'] == 1
        assert result['total_processed'] == 1
        assert 'date_range' in result
    
    @patch('analytics.intelligent_indexing_service.requests.get')
    def test_index_batch_api_error(self, mock_get):
        """Test batch indexing with API error"""
        # Mock API error
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = 'Repository not found'
        mock_get.return_value = mock_response
        
        # Mock process function
        def mock_process_function(data):
            return len(data)
        
        # Test batch indexing
        result = self.service.index_batch(
            fetch_function=lambda *args: [],
            process_function=mock_process_function,
            batch_size_days=30
        )
        
        # Should handle error gracefully
        assert result['status'] == 'success'
        assert result['processed'] == 0
        assert result['total_processed'] == 0
    
    def test_update_state(self):
        """Test state update after batch processing"""
        initial_total = self.service.state.total_indexed
        processed_count = 5
        
        self.service.update_state(processed_count)
        
        # Verify state was updated
        assert self.service.state.total_indexed == initial_total + processed_count
        assert self.service.state.last_indexed_at is not None
    
    def test_save_state(self):
        """Test state persistence"""
        # Modify state
        self.service.state.total_indexed = 100
        self.service.state.last_indexed_at = self.now
        
        # Save state
        self.service.save_state()
        
        # Verify state was saved to database
        saved_state = IndexingState.objects.filter(
            repository_full_name=self.repository_full_name,
            entity_type=self.entity_type
        ).first()
        
        assert saved_state is not None
        assert saved_state.total_indexed == 100
        assert saved_state.last_indexed_at == self.now
    
    def test_get_state_summary(self):
        """Test state summary generation"""
        # Set up state
        self.service.state.total_indexed = 150
        self.service.state.last_indexed_at = self.now - timedelta(hours=1)
        
        summary = self.service.get_state_summary()
        
        # Verify summary
        assert summary['total_indexed'] == 150
        assert summary['last_indexed_at'] == self.service.state.last_indexed_at
        assert summary['repository_full_name'] == self.repository_full_name
        assert summary['entity_type'] == self.entity_type
    
    def test_reset_state(self):
        """Test state reset functionality"""
        # Set up some state
        self.service.state.total_indexed = 100
        self.service.state.last_indexed_at = self.now
        
        # Reset state
        self.service.reset_state()
        
        # Verify state was reset
        assert self.service.state.total_indexed == 0
        assert self.service.state.last_indexed_at is None
    
    def test_get_progress_percentage(self):
        """Test progress percentage calculation"""
        # Set up state with some progress
        self.service.state.total_indexed = 75
        self.service.state.last_indexed_at = self.now - timedelta(hours=1)
        
        # Mock estimated total (would normally come from repository stats)
        estimated_total = 100
        
        progress = self.service.get_progress_percentage(estimated_total)
        
        # Verify progress calculation
        assert progress == 75 # 75/100 * 100
    
    def test_get_progress_percentage_zero_total(self):
        """Test progress percentage with zero estimated total"""
        self.service.state.total_indexed = 50
        
        progress = self.service.get_progress_percentage(0)
        
        # Should handle division by zero
        assert progress == 0
    
    def test_get_progress_percentage_no_progress(self):
        """Test progress percentage with no progress"""
        self.service.state.total_indexed = 0
        
        progress = self.service.get_progress_percentage(100)
        
        # Should return 0 for no progress
        assert progress == 0


class TestIntelligentIndexingServiceIntegration(BaseTestCase):
    """Integration tests for IntelligentIndexingService"""
    
    def setUp(self):
        super().setUp()
        self.repository_full_name = 'test-org/test-repo'
        self.entity_type = 'commits'
        self.github_token = 'ghp_test_token_12345'
        self.now = datetime.now(timezone.utc)
        
        # Create a mock repository for testing
        self.repository = self.create_mock_repository(
            full_name=self.repository_full_name
        )
        self.repository.save()
    
    def create_mock_repository(self, full_name='test-org/test-repo'):
        """Create a mock repository for testing"""
        mock_repo = Mock()
        mock_repo.id = 1
        mock_repo.full_name = full_name
        mock_repo.name = full_name.split('/')[-1]
        mock_repo.owner = full_name.split('/')[0]
        mock_repo.description = 'A test repository'
        mock_repo.private = False
        mock_repo.fork = False
        mock_repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_repo.updated_at = datetime(2023, 1, 15, tzinfo=timezone.utc)
        mock_repo.save.return_value = None
        return mock_repo
    
    def test_full_indexing_workflow(self):
        """Test complete indexing workflow"""
        service = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        # Mock fetch function
        def mock_fetch_function(repo_name, token, since_date, until_date):
            return [
                {
                    'sha': 'workflow_test_sha',
                    'commit': {
                        'author': {
                            'name': 'Workflow Test',
                            'email': 'workflow@test.com',
                            'date': '2023-01-15T10:30:00Z'
                        },
                        'committer': {
                            'name': 'Workflow Test',
                            'email': 'workflow@test.com',
                            'date': '2023-01-15T10:30:00Z'
                        },
                        'message': 'test: workflow test commit'
                    },
                    'stats': {'total': 50, 'additions': 30, 'deletions': 20},
                    'files': []
                }
            ]
        
        # Mock process function
        def mock_process_function(data):
            return len(data)
        
        # Test complete workflow
        result = service.index_batch(
            fetch_function=mock_fetch_function,
            process_function=mock_process_function,
            batch_size_days=30
        )
        
        # Verify workflow completed successfully
        assert result['status'] == 'success'
        assert result['processed'] == 1
        assert result['total_processed'] == 1
        
        # Verify state was updated
        assert service.state.total_indexed == 1
        assert service.state.last_indexed_at is not None
        
        # Verify state was saved
        saved_state = IndexingState.objects.filter(
            repository_id=self.repository.id,
            entity_type=self.entity_type
        ).first()
        
        assert saved_state is not None
        assert saved_state.total_indexed == 1
    
    def test_multiple_batches(self):
        """Test processing multiple batches"""
        service = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        # Mock fetch function that returns different data each time
        call_count = 0
        def mock_fetch_function(repo_name, token, since_date, until_date):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First batch
                return [
                    {
                        'sha': f'batch1_sha_{i}',
                        'commit': {
                            'author': {'name': 'Test', 'email': 'test@test.com', 'date': '2023-01-15T10:30:00Z'},
                            'committer': {'name': 'Test', 'email': 'test@test.com', 'date': '2023-01-15T10:30:00Z'},
                            'message': f'batch 1 commit {i}'
                        },
                        'stats': {'total': 10, 'additions': 5, 'deletions': 5},
                        'files': []
                    }
                    for i in range(3)
                ]
            else:
                # Second batch (empty)
                return []
        
        # Mock process function
        def mock_process_function(data):
            return len(data)
        
        # Process first batch
        result1 = service.index_batch(
            fetch_function=mock_fetch_function,
            process_function=mock_process_function,
            batch_size_days=30
        )
        
        assert result1['status'] == 'success'
        assert result1['processed'] == 3
        assert result1['total_processed'] == 3
        
        # Process second batch
        result2 = service.index_batch(
            fetch_function=mock_fetch_function,
            process_function=mock_process_function,
            batch_size_days=30
        )
        
        assert result2['status'] == 'success'
        assert result2['processed'] == 0
        assert result2['total_processed'] == 0
        
        # Verify total state
        assert service.state.total_indexed == 3
    
    def test_state_persistence_across_instances(self):
        """Test that state persists across different service instances"""
        # Create first instance and update state
        service1 = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        service1.state.total_indexed = 50
        service1.state.last_indexed_at = self.now
        service1.save_state()
        
        # Create second instance and verify state
        service2 = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        assert service2.state.total_indexed == 50
        assert service2.state.last_indexed_at == self.now
    
    def test_concurrent_state_updates(self):
        """Test handling of concurrent state updates"""
        service1 = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        service2 = IntelligentIndexingService(
            repository_id=self.repository.id,
            entity_type=self.entity_type,
            github_token=self.github_token
        )
        
        # Update state in both instances
        service1.state.total_indexed = 10
        service1.save_state()
        
        service2.state.total_indexed = 20
        service2.save_state()
        
        # Verify final state (last write wins)
        final_state = IndexingState.objects.filter(
            repository_id=self.repository.id,
            entity_type=self.entity_type
        ).first()
        
        assert final_state.total_indexed == 20
