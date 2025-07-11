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
    Start background indexing for an application
    """
    try:
        application = get_object_or_404(Application, id=application_id, owner=request.user)
        
        # Check if there's already a running indexing task for this application
        from datetime import datetime, timedelta
        
        # Look for recent tasks (last 2 hours) for this application
        cutoff_time = datetime.utcnow() - timedelta(hours=2)
        
        # Check for running tasks by looking at recent sync logs
        from .models import SyncLog
        recent_syncs = SyncLog.objects(
            application_id=application_id,
            started_at__gte=cutoff_time,
            status='running'
        )
        
        if recent_syncs.count() > 0:
            return JsonResponse({
                'success': False,
                'error': 'An indexing task is already running for this application. Please wait for it to complete.'
            })
        
        # Get total repositories count for progress tracking
        repositories = application.repositories.all()
        total_repos = repositories.count()
        
        if total_repos == 0:
            return JsonResponse({
                'success': False,
                'error': 'No repositories found for this application'
            })
        
        # Start background indexing task
        from django_q.tasks import async_task
        from analytics.tasks import background_indexing_task
        from datetime import datetime
        
        task_id = async_task(
            'analytics.tasks.background_indexing_task',
            application_id,
            request.user.id,
            group=f'indexing_{application_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
            timeout=7200  # 2 hour timeout
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Indexing started in background',
            'task_id': task_id,
            'total_repositories': total_repos
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
    Get current indexing progress for an application using Django-Q task status
    """
    try:
        application = get_object_or_404(Application, id=application_id, owner=request.user)
        
        # Get task ID from query params
        task_id = request.GET.get('task_id')
        if not task_id:
            return JsonResponse({
                'success': False,
                'error': 'Task ID is required'
            })
        
        # Get task status from Django-Q
        from django_q.models import Success, Failure
        from datetime import datetime, timedelta
        
        # Check if task is completed (success or failure)
        success_task = Success.objects.filter(id=task_id).first()
        failure_task = Failure.objects.filter(id=task_id).first()
        
        if success_task:
            # Task completed successfully
            result = success_task.result
            if isinstance(result, dict) and result.get('success'):
                return JsonResponse({
                    'success': True,
                    'progress': {
                        'percentage': 100.0,
                        'completed_repos': result.get('repositories_synced', 0),
                        'total_repos': result.get('total_repositories', 0),
                        'failed_repos': len(result.get('errors', [])),
                        'is_complete': True,
                        'is_running': False,
                        'result': result
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Task failed') if isinstance(result, dict) else 'Task failed'
                })
        
        elif failure_task:
            # Task failed
            return JsonResponse({
                'success': False,
                'error': str(failure_task.error) if failure_task.error else 'Task failed'
            })
        
        else:
            # Task is still running - get progress from sync logs
            from .models import SyncLog
            
            # Get recent sync logs (last 2 hours for background tasks to catch more activity)
            cutoff_time = datetime.utcnow() - timedelta(hours=2)
            recent_syncs = SyncLog.objects(
                application_id=application_id,
                started_at__gte=cutoff_time
            ).order_by('-started_at')
            
            total_repos = application.repositories.count()
            completed_repos = len([s for s in recent_syncs if s.status == 'completed'])
            failed_repos = len([s for s in recent_syncs if s.status == 'failed'])
            running_repos = len([s for s in recent_syncs if s.status == 'running'])
            
            # Debug information
            debug_info = {
                'total_syncs_found': len(recent_syncs),
                'completed_syncs': completed_repos,
                'failed_syncs': failed_repos,
                'running_syncs': running_repos,
                'total_repos': total_repos,
                'cutoff_time': cutoff_time.isoformat(),
                'task_id': task_id
            }
            
            # If no recent syncs found, the task might be in queue or just started
            if len(recent_syncs) == 0:
                # Check if there are any sync logs at all for this application
                all_syncs = SyncLog.objects(application_id=application_id).count()
                debug_info['all_syncs_count'] = all_syncs
                
                if all_syncs == 0:
                    # No sync logs at all - task might be in queue
                    return JsonResponse({
                        'success': True,
                        'progress': {
                            'percentage': 0.0,
                            'completed_repos': 0,
                            'total_repos': total_repos,
                            'failed_repos': 0,
                            'is_complete': False,
                            'is_running': True,
                            'status': 'Task is in queue or starting...',
                            'debug': debug_info
                        }
                    })
                else:
                    # There are sync logs but none recent - task might be processing
                    return JsonResponse({
                        'success': True,
                        'progress': {
                            'percentage': 0.0,
                            'completed_repos': 0,
                            'total_repos': total_repos,
                            'failed_repos': 0,
                            'is_complete': False,
                            'is_running': True,
                            'status': 'Task is processing repositories...',
                            'debug': debug_info
                        }
                    })
            
            # Calculate progress based on sync logs
            progress_percentage = (completed_repos / total_repos * 100) if total_repos > 0 else 0
            
            # Determine if task is still running
            is_running = running_repos > 0 or completed_repos < total_repos
            
            # Create status message
            if running_repos > 0:
                status = f'Currently processing repository {completed_repos + 1}/{total_repos}'
            elif completed_repos > 0:
                status = f'Processed {completed_repos}/{total_repos} repositories'
            else:
                status = 'Starting to process repositories...'
            
            return JsonResponse({
                'success': True,
                'progress': {
                    'percentage': round(progress_percentage, 1),
                    'completed_repos': completed_repos,
                    'total_repos': total_repos,
                    'failed_repos': failed_repos,
                    'is_complete': completed_repos >= total_repos,
                    'is_running': is_running,
                    'status': status,
                    'debug': debug_info
                }
            })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 