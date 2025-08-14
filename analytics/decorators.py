"""
Decorators for robust error handling in indexing tasks
"""
import logging
import functools
from typing import Callable, Any
from django_q.models import Task
from repositories.models import Repository

logger = logging.getLogger(__name__)


def handle_repository_not_found(func: Callable) -> Callable:
    """
    Decorator to handle Repository.DoesNotExist gracefully
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function that handles repository not found errors
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Repository.DoesNotExist as e:
            # Extract repository_id from function arguments
            repository_id = None
            if args and len(args) > 0:
                repository_id = args[0]
            elif 'repository_id' in kwargs:
                repository_id = kwargs['repository_id']
            
            logger.warning(f"Repository {repository_id} no longer exists, skipping indexing")
            return {
                'status': 'skipped',
                'repository_id': repository_id,
                'message': f'Repository {repository_id} no longer exists'
            }
        except Exception as e:
            # Re-raise other exceptions
            raise
    
    return wrapper


def handle_indexing_errors(func: Callable) -> Callable:
    """
    Decorator to handle common indexing errors gracefully
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function that handles indexing errors
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Indexing error in {func.__name__}: {error_msg}")
            
            # Extract repository_id from function arguments
            repository_id = None
            if args and len(args) > 0:
                repository_id = args[0]
            elif 'repository_id' in kwargs:
                repository_id = kwargs['repository_id']
            
            # Determine if this is a retryable error
            if _is_retryable_error(error_msg):
                logger.warning(f"Retryable error for repository {repository_id}, will retry")
                raise  # Let the task system handle retries
            else:
                logger.error(f"Non-retryable error for repository {repository_id}, marking as failed")
                return {
                    'status': 'error',
                    'repository_id': repository_id,
                    'error': error_msg,
                    'retryable': False
                }
    
    return wrapper


def _is_retryable_error(error_msg: str) -> bool:
    """
    Determine if an error is retryable
    
    Args:
        error_msg: Error message to analyze
        
    Returns:
        True if error should be retried, False otherwise
    """
    error_lower = error_msg.lower()
    
    # Retryable errors
    retryable_patterns = [
        'rate limit',
        '429',
        'timeout',
        'connection',
        'network',
        'temporary',
        'server error',
        '500',
        '502',
        '503',
        '504',
        '409 conflict',
        'too many requests',
        'quota exceeded'
    ]
    
    # Non-retryable errors
    non_retryable_patterns = [
        'not found',
        '404',
        'unauthorized',
        '401',
        'forbidden',
        '403',
        'bad request',
        '400',
        'repository not found',
        'invalid repository',
        'access denied'
    ]
    
    # Check for non-retryable errors first
    for pattern in non_retryable_patterns:
        if pattern in error_lower:
            return False
    
    # Check for retryable errors
    for pattern in retryable_patterns:
        if pattern in error_lower:
            return True
    
    # Default: retry unknown errors (conservative approach)
    return True


def monitor_indexing_performance(func: Callable) -> Callable:
    """
    Decorator to monitor indexing performance and log metrics
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with performance monitoring
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import time
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Extract repository_id for logging
            repository_id = None
            if args and len(args) > 0:
                repository_id = args[0]
            elif 'repository_id' in kwargs:
                repository_id = kwargs['repository_id']
            
            logger.info(f"Indexing completed for repository {repository_id} in {execution_time:.2f}s")
            
            # Log performance metrics if available
            if isinstance(result, dict) and 'processed' in result:
                items_per_second = result['processed'] / execution_time if execution_time > 0 else 0
                logger.info(f"Performance: {result['processed']} items processed at {items_per_second:.2f} items/sec")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Indexing failed after {execution_time:.2f}s: {str(e)}")
            raise
    
    return wrapper
