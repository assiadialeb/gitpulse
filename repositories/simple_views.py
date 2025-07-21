from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Repository
from analytics.unified_metrics_service import UnifiedMetricsService
import json


@login_required
def simple_repository_detail(request, repo_id):
    """Simplified repository detail view without complex error handling"""
    # Get repository
    repository = get_object_or_404(Repository, id=repo_id, owner=request.user)
    
    if not repository.is_indexed:
        context = {
            'repository': repository,
            'error_message': 'Repository is not indexed yet'
        }
        return render(request, 'repositories/detail.html', context)
    
    # Get metrics using unified service
    metrics_service = UnifiedMetricsService('repository', repo_id)
    all_metrics = metrics_service.get_all_metrics()
    
    # Extract specific metrics for template
    overall_stats = {
        'total_commits': all_metrics['total_commits'],
        'total_authors': all_metrics['total_developers'],
        'total_additions': all_metrics['lines_added'],
        'total_deletions': all_metrics['lines_deleted'],
        'net_lines': all_metrics['net_lines']
    }
    
    developer_activity = all_metrics['developer_activity_30d']
    commit_frequency = all_metrics['commit_frequency']
    release_frequency = all_metrics['release_frequency']
    total_releases = all_metrics['total_releases']
    pr_cycle_time = all_metrics['pr_cycle_time']
    commit_quality = all_metrics['commit_quality']
    commit_types = all_metrics['commit_type_distribution']
    pr_health_metrics = all_metrics['pr_health_metrics']
    top_contributors = all_metrics['top_contributors']
    activity_heatmap = all_metrics['commit_activity_by_hour']
    
    # Calculate PR cycle time statistics for template
    pr_cycle_time_median = pr_cycle_time.get('median_cycle_time_hours', 0)
    pr_cycle_time_avg = pr_cycle_time.get('avg_cycle_time_hours', 0)
    pr_cycle_time_count = pr_cycle_time.get('total_prs', 0)
    
    # Prepare chart data
    commit_types_counts = commit_types.get('counts', {}) if isinstance(commit_types, dict) else {}
    commit_type_labels = json.dumps(list(commit_types_counts.keys()))
    commit_type_values = json.dumps(list(commit_types_counts.values()))
    
    # Doughnut colors for commit types
    doughnut_colors = {
        'fix': '#4caf50',
        'feature': '#2196f3',
        'docs': '#ffeb3b',
        'refactor': '#ff9800',
        'test': '#9c27b0',
        'style': '#00bcd4',
        'chore': '#607d8b',
        'other': '#bdbdbd',
    }
    
    # Legend data for commit types
    legend_data = []
    for label, count in commit_types_counts.items():
        color = doughnut_colors.get(label, '#bdbdbd')
        legend_data.append({'label': label, 'count': count, 'color': color})
    
    # Hourly activity data
    hourly_data = activity_heatmap.get('hourly_data', {})
    activity_heatmap_data = json.dumps([int(hourly_data.get(str(hour), 0)) for hour in range(24)])
    
    # Build context
    context = {
        'repository': repository,
        'overall_stats': overall_stats,
        'developer_activity': developer_activity,
        'commit_frequency': commit_frequency,
        'release_frequency': release_frequency,
        'total_releases': total_releases,
        'pr_cycle_time_median': pr_cycle_time_median,
        'pr_cycle_time_avg': pr_cycle_time_avg,
        'pr_cycle_time_count': pr_cycle_time_count,
        'commit_quality': commit_quality,
        'commit_types': commit_types,
        'pr_health_metrics': pr_health_metrics,
        'top_contributors': top_contributors,
        'activity_heatmap': activity_heatmap,
        'commit_type_labels': commit_type_labels,
        'commit_type_values': commit_type_values,
        'commit_type_legend': legend_data,
        'doughnut_colors': doughnut_colors,
        'activity_heatmap_data': activity_heatmap_data,
    }
    
    return render(request, 'repositories/detail.html', context) 