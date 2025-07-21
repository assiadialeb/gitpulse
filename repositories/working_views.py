from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Repository
from analytics.unified_metrics_service import UnifiedMetricsService
import json


@login_required
def working_repository_detail(request, repo_id):
    """Working repository detail view with proper charts"""
    try:
        repository = Repository.objects.get(id=repo_id, owner=request.user)
    except Repository.DoesNotExist:
        messages.error(request, "Repository not found.")
        return redirect('repositories:list')
    
    if not repository.is_indexed:
        context = {
            'repository': repository,
            'error_message': 'Repository is not indexed yet'
        }
        return render(request, 'repositories/detail.html', context)
    
    try:
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
        
        # Prepare chart data for doughnut chart (like applications)
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
        
        # Bubble chart data
        bubble_chart = metrics_service.get_bubble_chart_data(days=30)
        bubble_chart_data = json.dumps(bubble_chart.get('datasets', []))
        
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
            'bubble_chart_data': bubble_chart_data,
        }
        
    except Exception as e:
        # If metrics calculation fails, provide empty data
        context = {
            'repository': repository,
            'overall_stats': {'total_commits': 0, 'total_authors': 0, 'total_additions': 0, 'total_deletions': 0, 'net_lines': 0},
            'developer_activity': {'developers': []},
            'commit_frequency': {'avg_commits_per_day': 0, 'recent_activity_score': 0, 'consistency_score': 0, 'overall_frequency_score': 0, 'commits_last_30_days': 0, 'commits_last_90_days': 0, 'days_since_last_commit': None, 'active_days': 0, 'total_days': 0},
            'release_frequency': {'releases_per_month': 0, 'releases_per_week': 0, 'total_releases': 0, 'period_days': 90},
            'total_releases': 0,
            'pr_cycle_time_median': 0,
            'pr_cycle_time_avg': 0,
            'pr_cycle_time_count': 0,
            'commit_quality': {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0},
            'commit_types': {'counts': {}},
            'pr_health_metrics': {'total_prs': 0, 'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0, 'prs_without_review': 0, 'prs_without_review_rate': 0, 'self_merged_prs': 0, 'self_merged_rate': 0, 'old_open_prs': 0, 'old_open_prs_rate': 0, 'avg_merge_time_hours': 0, 'median_merge_time_hours': 0},
            'top_contributors': [],
            'activity_heatmap': {'hourly_data': {}, 'total_commits': 0, 'period_days': 30},
            'commit_type_labels': json.dumps([]),
            'commit_type_values': json.dumps([]),
            'commit_type_legend': [],
            'doughnut_colors': {},
            'activity_heatmap_data': json.dumps([0] * 24),
            'error': str(e),
            'debug_error': True
        }
    
    return render(request, 'repositories/detail.html', context) 