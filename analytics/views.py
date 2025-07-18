"""
Views for analytics dashboard
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
import json
import logging

from applications.models import Application

logger = logging.getLogger(__name__)
from .analytics_service import AnalyticsService
from analytics.sync_service import SyncService
from analytics.models import Developer, DeveloperAlias
# from github.models import GitHubToken  # Deprecated - using PAT now


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
@require_http_methods(["GET"])
def api_commit_types(request, application_id):
    """
    API endpoint for commit type distribution
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    analytics = AnalyticsService(application_id)
    data = analytics.get_commit_type_distribution()
    
    return JsonResponse(data)


# These views have been removed as auto-grouping is no longer supported
# Use the global developer grouping in /developers/ instead


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
    
    try:
        # Start manual indexing task (one-shot)
        from django_q.tasks import async_task
        from .tasks import manual_indexing_task
        
        task_id = async_task(
            'analytics.tasks.manual_indexing_task',
            application_id,
            request.user.id,
            group=f'manual_indexing_{application_id}_{request.user.id}',
            timeout=7200  # 2 hour timeout
        )
        
        logger.info(f"Started manual indexing task {task_id} for application {application_id}")
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': 'Manual indexing started successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to start indexing for application {application_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def get_indexing_progress(request, application_id):
    """
    Get indexing progress for an application
    """
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({
            'success': False,
            'error': 'Task ID is required'
        })
    
    try:
        from django_q.models import Success, Failure
        from django_q.tasks import fetch
        
        # Try to get the task result
        result = fetch(task_id)
        
        if result is None:
            # Task is still running
            return JsonResponse({
                'success': True,
                'progress': {
                    'percentage': 50,  # Default progress
                    'status': 'Indexing in progress...',
                    'is_running': True,
                    'is_complete': False
                }
            })
        
        # Task completed
        if result.success:
            return JsonResponse({
                'success': True,
                'progress': {
                    'percentage': 100,
                    'status': 'Indexing completed!',
                    'is_running': False,
                    'is_complete': True,
                    'result': result.result
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Task failed: {result.result}'
            })
            
    except Exception as e:
        logger.error(f"Error checking progress for task {task_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Error checking progress: {str(e)}'
        }) 

@login_required
def delete_developer(request, application_id, developer_id):
    """Delete a developer"""
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    try:
        from .models import Developer
        developer = Developer.objects.get(id=developer_id, application_id=application_id)
        developer_name = developer.primary_name
        developer.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Developer "{developer_name}" deleted successfully'
        })
        
    except Developer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Developer not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def rename_developer(request, application_id, developer_id):
    """Rename a developer"""
    application = get_object_or_404(Application, id=application_id, owner=request.user)
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method allowed'
        })
    
    try:
        from .models import Developer
        developer = Developer.objects.get(id=developer_id, application_id=application_id)
        
        new_name = request.POST.get('new_name')
        if not new_name:
            return JsonResponse({
                'success': False,
                'error': 'New name is required'
            })
        
        old_name = developer.primary_name
        developer.primary_name = new_name
        developer.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Developer renamed from "{old_name}" to "{new_name}"'
        })
        
    except Developer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Developer not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }) 

@login_required
def api_auto_group_developers(request, application_id):
    """API endpoint to automatically group developers"""
    if request.method == 'POST':
        try:
            from .developer_grouping_service import DeveloperGroupingService
            
            grouping_service = DeveloperGroupingService(application_id)
            result = grouping_service.auto_group_developers()
            
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error in auto-grouping: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405) 

@login_required
def api_merge_existing_developers(request, application_id):
    """API endpoint to merge existing developers that should be combined"""
    if request.method == 'POST':
        try:
            from .developer_grouping_service import DeveloperGroupingService
            
            grouping_service = DeveloperGroupingService(application_id)
            result = grouping_service.merge_existing_developers()
            
            return JsonResponse(result)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error merging developers: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405) 