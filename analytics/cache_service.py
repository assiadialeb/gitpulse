"""
Cache service for analytics metrics
"""
from django.core.cache import cache
from django.conf import settings
import hashlib
import json
from typing import Dict, Any, Optional


class AnalyticsCacheService:
    """Service for caching analytics metrics"""
    
    @staticmethod
    def _generate_cache_key(prefix: str, app_id: int, **kwargs) -> str:
        """Generate a unique cache key"""
        # Create a hash of the parameters to ensure uniqueness
        params_str = json.dumps(kwargs, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"analytics:{prefix}:{app_id}:{params_hash}"
    
    # PR Health Metrics
    @staticmethod
    def get_pr_health_metrics(app_id: int) -> Optional[Dict[str, Any]]:
        """Get PR health metrics from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("pr_health", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_pr_health_metrics(app_id: int, metrics: Dict[str, Any]) -> None:
        """Set PR health metrics in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("pr_health", app_id)
        timeout = getattr(settings, 'PR_METRICS_CACHE_TIMEOUT', 1800)  # 30 minutes
        cache.set(cache_key, metrics, timeout)
    
    # Application Quality Metrics
    @staticmethod
    def get_quality_metrics(app_id: int) -> Optional[Dict[str, Any]]:
        """Get quality metrics from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("quality_metrics", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_quality_metrics(app_id: int, metrics: Dict[str, Any]) -> None:
        """Set quality metrics in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("quality_metrics", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, metrics, timeout)
    
    # Overall Stats
    @staticmethod
    def get_overall_stats(app_id: int) -> Optional[Dict[str, Any]]:
        """Get overall stats from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("overall_stats", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_overall_stats(app_id: int, stats: Dict[str, Any]) -> None:
        """Set overall stats in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("overall_stats", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, stats, timeout)
    
    # Developer Activity
    @staticmethod
    def get_developer_activity(app_id: int, days: int = 30) -> Optional[Dict[str, Any]]:
        """Get developer activity from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("developer_activity", app_id, days=days)
        return cache.get(cache_key)
    
    @staticmethod
    def set_developer_activity(app_id: int, activity: Dict[str, Any], days: int = 30) -> None:
        """Set developer activity in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("developer_activity", app_id, days=days)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, activity, timeout)
    
    # Commit Frequency
    @staticmethod
    def get_commit_frequency(app_id: int) -> Optional[Dict[str, Any]]:
        """Get commit frequency from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_frequency", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_commit_frequency(app_id: int, frequency: Dict[str, Any]) -> None:
        """Set commit frequency in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_frequency", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, frequency, timeout)
    
    # Release Frequency
    @staticmethod
    def get_release_frequency(app_id: int, period_days: int = 30) -> Optional[Dict[str, Any]]:
        """Get release frequency from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("release_frequency", app_id, period_days=period_days)
        return cache.get(cache_key)
    
    @staticmethod
    def set_release_frequency(app_id: int, frequency: Dict[str, Any], period_days: int = 30) -> None:
        """Set release frequency in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("release_frequency", app_id, period_days=period_days)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, frequency, timeout)
    
    # PR Cycle Times
    @staticmethod
    def get_pr_cycle_times(app_id: int) -> Optional[Dict[str, Any]]:
        """Get PR cycle times from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("pr_cycle_times", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_pr_cycle_times(app_id: int, cycle_times: Dict[str, Any]) -> None:
        """Set PR cycle times in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("pr_cycle_times", app_id)
        timeout = getattr(settings, 'PR_METRICS_CACHE_TIMEOUT', 1800)  # 30 minutes
        cache.set(cache_key, cycle_times, timeout)
    
    # Code Distribution
    @staticmethod
    def get_code_distribution(app_id: int) -> Optional[Dict[str, Any]]:
        """Get code distribution from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("code_distribution", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_code_distribution(app_id: int, distribution: Dict[str, Any]) -> None:
        """Set code distribution in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("code_distribution", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, distribution, timeout)
    
    # Activity Heatmap
    @staticmethod
    def get_activity_heatmap(app_id: int, days: int = 90) -> Optional[Dict[str, Any]]:
        """Get activity heatmap from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("activity_heatmap", app_id, days=days)
        return cache.get(cache_key)
    
    @staticmethod
    def set_activity_heatmap(app_id: int, heatmap: Dict[str, Any], days: int = 90) -> None:
        """Set activity heatmap in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("activity_heatmap", app_id, days=days)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, heatmap, timeout)
    
    # Bubble Chart
    @staticmethod
    def get_bubble_chart(app_id: int, days: int = 30) -> Optional[Dict[str, Any]]:
        """Get bubble chart data from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("bubble_chart", app_id, days=days)
        return cache.get(cache_key)
    
    @staticmethod
    def set_bubble_chart(app_id: int, chart_data: Dict[str, Any], days: int = 30) -> None:
        """Set bubble chart data in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("bubble_chart", app_id, days=days)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, chart_data, timeout)
    
    # Commit Quality
    @staticmethod
    def get_commit_quality(app_id: int) -> Optional[Dict[str, Any]]:
        """Get commit quality metrics from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_quality", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_commit_quality(app_id: int, quality: Dict[str, Any]) -> None:
        """Set commit quality metrics in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_quality", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, quality, timeout)
    
    # Commit Types
    @staticmethod
    def get_commit_types(app_id: int) -> Optional[Dict[str, Any]]:
        """Get commit type distribution from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_types", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_commit_types(app_id: int, types: Dict[str, Any]) -> None:
        """Set commit type distribution in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("commit_types", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, types, timeout)
    
    # Total Releases
    @staticmethod
    def get_total_releases(app_id: int) -> Optional[int]:
        """Get total releases from cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("total_releases", app_id)
        return cache.get(cache_key)
    
    @staticmethod
    def set_total_releases(app_id: int, total: int) -> None:
        """Set total releases in cache"""
        cache_key = AnalyticsCacheService._generate_cache_key("total_releases", app_id)
        timeout = getattr(settings, 'ANALYTICS_CACHE_TIMEOUT', 3600)  # 1 hour
        cache.set(cache_key, total, timeout)
    
    # Cache invalidation
    @staticmethod
    def invalidate_app_cache(app_id: int) -> None:
        """Invalidate all cache for a specific application"""
        # This is a simple approach - in production you might want more granular control
        cache_keys_to_delete = [
            f"analytics:pr_health:{app_id}:*",
            f"analytics:quality_metrics:{app_id}:*",
            f"analytics:overall_stats:{app_id}:*",
            f"analytics:developer_activity:{app_id}:*",
            f"analytics:commit_frequency:{app_id}:*",
            f"analytics:release_frequency:{app_id}:*",
            f"analytics:pr_cycle_times:{app_id}:*",
            f"analytics:code_distribution:{app_id}:*",
            f"analytics:activity_heatmap:{app_id}:*",
            f"analytics:bubble_chart:{app_id}:*",
            f"analytics:commit_quality:{app_id}:*",
            f"analytics:commit_types:{app_id}:*",
            f"analytics:total_releases:{app_id}:*",
        ]
        
        # Note: Django's cache doesn't support pattern deletion by default
        # This is a simplified approach - you might need to track keys manually
        # or use a more sophisticated cache backend like Redis
        
        # For now, we'll just clear the entire cache when new data is added
        # This is not ideal but works for the current setup
        cache.clear()
    
    @staticmethod
    def is_cache_enabled() -> bool:
        """Check if caching is enabled"""
        return hasattr(settings, 'CACHES') and 'default' in settings.CACHES


def cached_metrics(func):
    """Decorator to cache expensive metric calculations"""
    def wrapper(app_id: int, *args, **kwargs):
        # Check if cache is enabled
        if not AnalyticsCacheService.is_cache_enabled():
            return func(app_id, *args, **kwargs)
        
        # Try to get from cache first
        cached_result = AnalyticsCacheService.get_pr_health_metrics(app_id)
        if cached_result is not None:
            return cached_result
        
        # Calculate if not in cache
        result = func(app_id, *args, **kwargs)
        
        # Store in cache
        if result is not None:
            AnalyticsCacheService.set_pr_health_metrics(app_id, result)
        
        return result
    
    return wrapper 