import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from repositories.models import Repository
from analytics.decorators import (
    handle_repository_not_found,
    handle_indexing_errors,
    monitor_indexing_performance,
    _is_retryable_error
)


class TestDecorators(TestCase):
    """Test cases for analytics decorators"""

    def setUp(self):
        """Set up test fixtures"""
        self.user = Mock()
        self.repository = Mock()
        self.repository.id = 123
        self.repository.full_name = 'test-org/test-repo'

    def test_handle_repository_not_found_success(self):
        """Test handle_repository_not_found decorator with successful execution"""
        @handle_repository_not_found
        def test_func(repository_id):
            return {'status': 'success', 'data': 'test_data'}
        
        result = test_func(123)
        self.assertEqual(result, {'status': 'success', 'data': 'test_data'})

    def test_handle_repository_not_found_repository_does_not_exist(self):
        """Test handle_repository_not_found decorator with Repository.DoesNotExist"""
        @handle_repository_not_found
        def test_func(repository_id):
            raise Repository.DoesNotExist("Repository not found")
        
        result = test_func(123)
        expected = {
            'status': 'skipped',
            'repository_id': 123,
            'message': 'Repository 123 no longer exists'
        }
        self.assertEqual(result, expected)

    def test_handle_repository_not_found_repository_does_not_exist_kwargs(self):
        """Test handle_repository_not_found decorator with repository_id in kwargs"""
        @handle_repository_not_found
        def test_func(some_arg, repository_id=None):
            raise Repository.DoesNotExist("Repository not found")
        
        result = test_func('test', repository_id=456)
        expected = {
            'status': 'skipped',
            'repository_id': 'test',  # First positional argument
            'message': 'Repository test no longer exists'
        }
        self.assertEqual(result, expected)

    def test_handle_repository_not_found_other_exception(self):
        """Test handle_repository_not_found decorator with other exceptions"""
        @handle_repository_not_found
        def test_func(repository_id):
            raise ValueError("Some other error")
        
        with self.assertRaises(ValueError):
            test_func(123)

    def test_handle_indexing_errors_success(self):
        """Test handle_indexing_errors decorator with successful execution"""
        @handle_indexing_errors
        def test_func(repository_id):
            return {'status': 'success', 'data': 'test_data'}
        
        result = test_func(123)
        self.assertEqual(result, {'status': 'success', 'data': 'test_data'})

    @patch('analytics.decorators.logger')
    def test_handle_indexing_errors_retryable_error(self, mock_logger):
        """Test handle_indexing_errors decorator with retryable error"""
        @handle_indexing_errors
        def test_func(repository_id):
            raise Exception("Rate limit exceeded")
        
        with self.assertRaises(Exception):
            test_func(123)
        
        # Verify error was logged
        mock_logger.error.assert_called_once()
        mock_logger.warning.assert_called_once()

    @patch('analytics.decorators.logger')
    def test_handle_indexing_errors_non_retryable_error(self, mock_logger):
        """Test handle_indexing_errors decorator with non-retryable error"""
        @handle_indexing_errors
        def test_func(repository_id):
            raise Exception("Repository not found")
        
        result = test_func(123)
        expected = {
            'status': 'error',
            'repository_id': 123,
            'error': 'Repository not found',
            'retryable': False
        }
        self.assertEqual(result, expected)
        
        # Verify error was logged
        mock_logger.error.assert_called()

    @patch('analytics.decorators.logger')
    def test_handle_indexing_errors_kwargs(self, mock_logger):
        """Test handle_indexing_errors decorator with repository_id in kwargs"""
        @handle_indexing_errors
        def test_func(some_arg, repository_id=None):
            raise Exception("Repository not found")
        
        result = test_func('test', repository_id=456)
        expected = {
            'status': 'error',
            'repository_id': 'test',  # First positional argument
            'error': 'Repository not found',
            'retryable': False
        }
        self.assertEqual(result, expected)

    @patch('analytics.decorators.logger')
    def test_monitor_indexing_performance_success(self, mock_logger):
        """Test monitor_indexing_performance decorator with successful execution"""
        @monitor_indexing_performance
        def test_func(repository_id):
            time.sleep(0.01)  # Small delay to measure
            return {'status': 'success', 'processed': 100}
        
        result = test_func(123)
        self.assertEqual(result, {'status': 'success', 'processed': 100})
        
        # Verify performance was logged
        mock_logger.info.assert_called()
        # Check that performance metrics were logged
        performance_logs = [call for call in mock_logger.info.call_args_list 
                          if 'Performance:' in str(call)]
        self.assertTrue(len(performance_logs) > 0)

    @patch('analytics.decorators.logger')
    def test_monitor_indexing_performance_error(self, mock_logger):
        """Test monitor_indexing_performance decorator with error"""
        @monitor_indexing_performance
        def test_func(repository_id):
            time.sleep(0.01)  # Small delay to measure
            raise Exception("Test error")
        
        with self.assertRaises(Exception):
            test_func(123)
        
        # Verify error was logged with timing
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("failed after", error_call)
        self.assertIn("Test error", error_call)

    @patch('analytics.decorators.logger')
    def test_monitor_indexing_performance_no_processed_field(self, mock_logger):
        """Test monitor_indexing_performance decorator without processed field"""
        @monitor_indexing_performance
        def test_func(repository_id):
            return {'status': 'success'}
        
        result = test_func(123)
        self.assertEqual(result, {'status': 'success'})
        
        # Verify basic completion was logged
        mock_logger.info.assert_called()
        completion_logs = [call for call in mock_logger.info.call_args_list 
                          if 'completed' in str(call)]
        self.assertTrue(len(completion_logs) > 0)

    def test_is_retryable_error_rate_limit(self):
        """Test _is_retryable_error with rate limit errors"""
        retryable_errors = [
            "Rate limit exceeded",
            "429 Too Many Requests",
            "Connection timeout",
            "Network error",
            "Temporary server error",
            "500 Internal Server Error",
            "502 Bad Gateway",
            "503 Service Unavailable",
            "504 Gateway Timeout",
            "409 Conflict",
            "Too many requests",
            "Quota exceeded"
        ]
        
        for error in retryable_errors:
            with self.subTest(error=error):
                self.assertTrue(_is_retryable_error(error))

    def test_is_retryable_error_non_retryable(self):
        """Test _is_retryable_error with non-retryable errors"""
        non_retryable_errors = [
            "Repository not found",
            "404 Not Found",
            "Unauthorized access",
            "401 Unauthorized",
            "Forbidden access",
            "403 Forbidden",
            "Bad request",
            "400 Bad Request",
            "Invalid repository",
            "Access denied"
        ]
        
        for error in non_retryable_errors:
            with self.subTest(error=error):
                self.assertFalse(_is_retryable_error(error))

    def test_is_retryable_error_unknown_error(self):
        """Test _is_retryable_error with unknown errors (should default to retryable)"""
        unknown_errors = [
            "Some random error",
            "Unexpected behavior",
            "Custom error message"
        ]
        
        for error in unknown_errors:
            with self.subTest(error=error):
                self.assertTrue(_is_retryable_error(error))

    def test_is_retryable_error_case_insensitive(self):
        """Test _is_retryable_error is case insensitive"""
        # Test retryable errors
        self.assertTrue(_is_retryable_error("RATE LIMIT EXCEEDED"))
        self.assertTrue(_is_retryable_error("rate limit exceeded"))
        self.assertTrue(_is_retryable_error("Rate Limit Exceeded"))
        
        # Test non-retryable errors
        self.assertFalse(_is_retryable_error("NOT FOUND"))
        self.assertFalse(_is_retryable_error("not found"))
        self.assertFalse(_is_retryable_error("Not Found"))

    def test_decorator_preserves_function_metadata(self):
        """Test that decorators preserve function metadata"""
        @handle_repository_not_found
        @handle_indexing_errors
        @monitor_indexing_performance
        def test_func(repository_id):
            """Test function docstring"""
            return {'status': 'success'}
        
        # Check that function name and docstring are preserved
        self.assertEqual(test_func.__name__, 'test_func')
        self.assertEqual(test_func.__doc__, 'Test function docstring')

    def test_decorator_chain_order(self):
        """Test that decorators work correctly when chained"""
        execution_order = []
        
        @handle_repository_not_found
        @handle_indexing_errors
        @monitor_indexing_performance
        def test_func(repository_id):
            execution_order.append('function')
            return {'status': 'success'}
        
        result = test_func(123)
        
        # Verify function was executed
        self.assertEqual(execution_order, ['function'])
        self.assertEqual(result, {'status': 'success'})

    @patch('analytics.decorators.logger')
    def test_decorator_chain_with_error(self, mock_logger):
        """Test decorator chain with error handling"""
        @monitor_indexing_performance
        @handle_indexing_errors
        @handle_repository_not_found
        def test_func(repository_id):
            raise Repository.DoesNotExist("Repository not found")
        
        result = test_func(123)
        
        # Should be handled by handle_repository_not_found (last decorator in chain)
        expected = {
            'status': 'skipped',
            'repository_id': 123,
            'message': 'Repository 123 no longer exists'
        }
        self.assertEqual(result, expected)
