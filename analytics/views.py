"""
Views for analytics dashboard
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
import json

from applications.models import Application
from .analytics_service import AnalyticsService
from analytics.sync_service import SyncService
from analytics.models import DeveloperGroup, DeveloperAlias


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
def group_developers(request, application_id):
    """
    Manually trigger developer grouping and show results
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # Initialize analytics service
    analytics = AnalyticsService(application_id)
    
    # Group developers
    grouping_results = analytics.group_developers()
    grouped_developers = analytics.get_grouped_developers()
    individual_developers = analytics.get_individual_developers()
    
    context = {
        'application': application,
        'grouping_results': grouping_results,
        'grouped_developers': grouped_developers,
        'individual_developers': individual_developers,
    }
    
    return render(request, 'analytics/group_developers.html', context)


@login_required
@require_http_methods(["POST"])
def api_group_developers(request, application_id):
    """
    API endpoint to trigger developer grouping
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    analytics = AnalyticsService(application_id)
    results = analytics.group_developers()
    
    return JsonResponse(results)


@login_required
@require_http_methods(["POST"])
def api_manual_group_developers(request, application_id):
    """
    API endpoint to manually group developers
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    try:
        data = json.loads(request.body)
        analytics = AnalyticsService(application_id)
        results = analytics.manually_group_developers(data)
        
        return JsonResponse(results)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def start_indexing(request, application_id):
    """
    Start indexing for an application
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # Initialize sync service
    sync_service = SyncService(user_id=request.user.id)
    
    # Start indexing
    result = sync_service.sync_application_repositories_with_progress(application_id)
    
    return JsonResponse(result)


@login_required
def get_indexing_progress(request, application_id):
    """
    Get indexing progress for an application
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    # For now, return a simple response since get_sync_progress doesn't exist
    # This can be implemented later if needed
    return JsonResponse({
        'success': True,
        'progress': {
            'percentage': 0,
            'status': 'Progress tracking not implemented yet'
        }
    }) 

@login_required
@require_POST
def delete_group(request, application_id, group_id):
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    try:
        group = DeveloperGroup.objects.get(id=group_id, application_id=application_id)
    except DeveloperGroup.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Group not found'}, status=404)
        return redirect('analytics:group_developers', application_id=application_id)
    try:
        DeveloperAlias.objects.filter(group=group).delete()
        group.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('analytics:group_developers', application_id=application_id)
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        return redirect('analytics:group_developers', application_id=application_id)

@login_required
@require_POST
def rename_group(request, application_id, group_id):
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    try:
        group = DeveloperGroup.objects.get(id=group_id, application_id=application_id)
    except DeveloperGroup.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Group not found'}, status=404)
        return redirect('analytics:group_developers', application_id=application_id)
    # Robustly handle AJAX/JSON and form POST
    data = None
    if request.headers.get('content-type', '').startswith('application/json'):
        try:
            data = json.loads(request.body.decode())
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Invalid JSON: {e}'}, status=400)
    else:
        data = request.POST
    name = data.get('primary_name') if data else None
    email = data.get('primary_email') if data else None
    if not name and not email:
        return JsonResponse({'success': False, 'error': 'No data provided'}, status=400)
    if name:
        group.primary_name = name
    if email:
        group.primary_email = email
    try:
        group.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'primary_name': group.primary_name, 'primary_email': group.primary_email})
        return redirect('analytics:group_developers', application_id=application_id)
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        return redirect('analytics:group_developers', application_id=application_id) 