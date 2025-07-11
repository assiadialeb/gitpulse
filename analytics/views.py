"""
Views for analytics dashboard
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from applications.models import Application
from .analytics_service import AnalyticsService


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