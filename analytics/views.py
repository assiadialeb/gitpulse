"""
Views for analytics dashboard
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from applications.models import Application
from .analytics_service import AnalyticsService
from analytics.sync_service import SyncService


@login_required
def application_dashboard(request, application_id):
    """
    Display analytics dashboard for an application
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # Initialize analytics service
    analytics = AnalyticsService(application_id)
    
    # Get analytics data
    context = {
        'application': application,
        'overall_stats': analytics.get_overall_stats(),
        'developer_activity': analytics.get_developer_activity(days=30),
        'activity_heatmap': analytics.get_activity_heatmap(days=90),
        'code_distribution': analytics.get_code_distribution(),
        'commit_quality': analytics.get_commit_quality_metrics(),
    }
    
    return render(request, 'analytics/dashboard.html', context)


@login_required
@require_http_methods(["GET"])
def api_developer_activity(request, application_id):
    """
    API endpoint for developer activity data
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # Get period from query params
    days = int(request.GET.get('days', 30))
    
    analytics = AnalyticsService(application_id)
    data = analytics.get_developer_activity(days=days)
    
    return JsonResponse(data)


@login_required
@require_http_methods(["GET"])
def api_activity_heatmap(request, application_id):
    """
    API endpoint for activity heatmap data
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # Get period from query params
    days = int(request.GET.get('days', 90))
    
    analytics = AnalyticsService(application_id)
    data = analytics.get_activity_heatmap(days=days)
    
    return JsonResponse(data)


@login_required
@require_http_methods(["GET"])
def api_code_distribution(request, application_id):
    """
    API endpoint for code distribution data
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    analytics = AnalyticsService(application_id)
    data = analytics.get_code_distribution()
    
    return JsonResponse(data)


@login_required
@require_http_methods(["GET"])
def api_commit_quality(request, application_id):
    """
    API endpoint for commit quality metrics
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    analytics = AnalyticsService(application_id)
    data = analytics.get_commit_quality_metrics()
    
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def start_indexing(request, application_id):
    """
    Start manual indexing/backfill for an application
    """
    try:
        application = get_object_or_404(Application, id=application_id, owner=request.user)
        
        # Initialize sync service with user ID
        sync_service = SyncService(request.user.id)
        
        # Get total repositories count for progress tracking
        repositories = application.repositories.all()
        total_repos = repositories.count()
        
        if total_repos == 0:
            return JsonResponse({
                'success': False,
                'error': 'No repositories found for this application'
            })
        
        # Start full backfill process for all repositories with progress tracking
        result = sync_service.sync_application_repositories_with_progress(application_id, sync_type='full')
        
        return JsonResponse({
            'success': True,
            'message': 'Indexing completed successfully',
            'repositories_synced': result['repositories_synced'],
            'total_commits_new': result['total_commits_new'],
            'total_commits_updated': result['total_commits_updated'],
            'total_repositories': total_repos,
            'errors': result.get('errors', [])
        })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_indexing_progress(request, application_id):
    """
    Get current indexing progress for an application
    """
    try:
        application = get_object_or_404(Application, id=application_id, owner=request.user)
        
        # Get progress from sync logs
        from .models import SyncLog
        from datetime import datetime, timedelta
        
        # Get recent sync logs (last 10 minutes)
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        recent_syncs = SyncLog.objects(
            application_id=application_id,
            started_at__gte=cutoff_time
        ).order_by('-started_at')
        
        total_repos = application.repositories.count()
        completed_repos = len([s for s in recent_syncs if s.status == 'completed'])
        failed_repos = len([s for s in recent_syncs if s.status == 'failed'])
        running_repos = len([s for s in recent_syncs if s.status == 'running'])
        
        progress_percentage = (completed_repos / total_repos * 100) if total_repos > 0 else 0
        
        return JsonResponse({
            'success': True,
            'progress': {
                'percentage': round(progress_percentage, 1),
                'completed_repos': completed_repos,
                'total_repos': total_repos,
                'failed_repos': failed_repos,
                'is_complete': completed_repos >= total_repos,
                'is_running': running_repos > 0
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 