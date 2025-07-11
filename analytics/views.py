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
from analytics.models import DeveloperGroup, DeveloperAlias
from github.models import GitHubToken


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
    
    try:
        # Start background indexing task
        from django_q.tasks import async_task
        from .tasks import background_indexing_task
        
        task_id = async_task(
            'analytics.tasks.background_indexing_task',
            application_id,
            request.user.id,
            None,  # task_id will be generated
            group=f'indexing_{application_id}_{request.user.id}',
            timeout=7200  # 2 hour timeout
        )
        
        logger.info(f"Started background indexing task {task_id} for application {application_id}")
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'message': 'Indexing started successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to start indexing for application {application_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def get_rate_limit_status(request):
    """
    Get current rate limit status for the user
    """
    try:
        # Get user's GitHub token
        github_token = GitHubToken.objects.get(user_id=request.user.id)
        
        # Get pending rate limit resets
        from .models import RateLimitReset
        pending_resets = RateLimitReset.objects.filter(
            user_id=request.user.id,
            status__in=['pending', 'scheduled']
        ).order_by('rate_limit_reset_time')
        
        reset_info = []
        for reset in pending_resets:
            reset_info.append({
                'id': str(reset.id),
                'task_type': reset.pending_task_type,
                'reset_time': reset.rate_limit_reset_time.isoformat(),
                'time_until_reset': reset.time_until_reset,
                'status': reset.status,
                'original_task_id': reset.original_task_id
            })
        
        return JsonResponse({
            'success': True,
            'github_username': github_token.github_username,
            'pending_resets': reset_info,
            'total_pending': len(reset_info)
        })
        
    except GitHubToken.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No GitHub token found for user'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def cancel_rate_limit_restart(request, reset_id):
    """
    Cancel a pending rate limit restart
    """
    try:
        from .models import RateLimitReset
        from django_q.models import Schedule as ScheduleModel
        
        # Get the rate limit reset
        rate_limit_reset = RateLimitReset.objects.get(
            id=reset_id,
            user_id=request.user.id
        )
        
        # Cancel the scheduled restart
        try:
            schedule = ScheduleModel.objects.get(name=f"rate_limit_restart_{reset_id}")
            schedule.delete()
        except ScheduleModel.DoesNotExist:
            pass
        
        # Update status
        rate_limit_reset.status = 'cancelled'
        rate_limit_reset.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Rate limit restart cancelled successfully'
        })
        
    except RateLimitReset.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Rate limit reset not found'
        })
    except Exception as e:
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