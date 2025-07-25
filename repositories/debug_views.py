from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Repository
from analytics.unified_metrics_service import UnifiedMetricsService


@login_required
def repository_debug(request, repo_id):
    """Debug view for repository metrics"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        return JsonResponse({'error': 'Repository not found'}, status=404)
    
    if not repository.is_indexed:
        return JsonResponse({'error': 'Repository not indexed'}, status=400)
    
    try:
        # Use unified metrics service for repository
        metrics_service = UnifiedMetricsService('repository', repo_id)
        all_metrics = metrics_service.get_all_metrics()
        
        debug_data = {
            'repository_id': repository.id,
            'repository_name': repository.full_name,
            'repository_indexed': repository.is_indexed,
            'metrics_keys': list(all_metrics.keys()),
            'total_commits': all_metrics.get('total_commits'),
            'total_developers': all_metrics.get('total_developers'),
            'lines_added': all_metrics.get('lines_added'),
            'lines_deleted': all_metrics.get('lines_deleted'),
            'net_lines': all_metrics.get('net_lines'),
            'commit_frequency': all_metrics.get('commit_frequency'),
            'developer_activity': all_metrics.get('developer_activity_30d'),
            'total_releases': all_metrics.get('total_releases'),
            'commit_quality': all_metrics.get('commit_quality'),
            'commit_types': all_metrics.get('commit_type_distribution'),
            'pr_health': all_metrics.get('pr_health_metrics'),
            'top_contributors': all_metrics.get('top_contributors'),
            'status': 'success'
        }
        
    except Exception as e:
        import traceback
        debug_data = {
            'repository_id': repository.id,
            'repository_name': repository.full_name,
            'error': str(e),
            'error_type': str(type(e)),
            'traceback': traceback.format_exc(),
            'status': 'error'
        }
    
    import json
    from django.http import HttpResponse
    return HttpResponse(
        json.dumps(debug_data, indent=2),
        content_type='application/json'
    ) 