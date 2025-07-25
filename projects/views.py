from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Project
from repositories.models import Repository


@login_required
def project_list(request):
    """List all projects"""
    projects = Project.objects.all().order_by('name')
    
    context = {
        'projects': projects,
    }
    return render(request, 'projects/list.html', context)


@login_required
def project_detail(request, project_id):
    """Show project details with aggregated stats"""
    project = get_object_or_404(Project, id=project_id)
    
    # Get date range parameters
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    
    # Parse dates if provided
    from datetime import datetime, timedelta
    from django.utils import timezone
    import pytz
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            # Add one day to end_date to include the full day
            end_dt = end_dt + timedelta(days=1)
        except ValueError:
            # Default to last 30 days if invalid dates
            end_dt = timezone.now()
            start_dt = end_dt - timedelta(days=30)
    else:
        # Default to last 30 days
        end_dt = timezone.now()
        start_dt = end_dt - timedelta(days=30)
    
    # Get all repositories in this project
    repositories = project.repositories.all()
    
    # Get repository full names for MongoDB queries
    repo_full_names = [repo.full_name for repo in repositories]
    
    # Import analytics models for additional stats
    from analytics.models import Commit, Release, PullRequest, Deployment
    
    # Calculate commits from MongoDB (filtered by date range)
    recent_commits = Commit.objects.filter(
        repository_full_name__in=repo_full_names,
        authored_date__gte=start_dt,
        authored_date__lt=end_dt
    )
    total_commits = recent_commits.count()
    total_repositories = len(repositories)
    total_stars = sum(repo.stars for repo in repositories)
    total_forks = sum(repo.forks for repo in repositories)
    
    # Get repository full names for MongoDB queries
    repo_full_names = [repo.full_name for repo in repositories]
    
    # Import analytics models for additional stats
    from analytics.models import Commit, Release, PullRequest, Deployment
    
    # Calculate additional metrics from MongoDB with date filtering
    total_releases = Release.objects.filter(
        repository_full_name__in=repo_full_names,
        published_at__gte=start_dt,
        published_at__lt=end_dt
    ).count()
    
    total_deployments = Deployment.objects.filter(
        repository_full_name__in=repo_full_names,
        created_at__gte=start_dt,
        created_at__lt=end_dt
    ).count()
    
    # Calculate PR cycle time (filtered by date)
    prs = PullRequest.objects.filter(
        repository_full_name__in=repo_full_names,
        created_at__ne=None,
        closed_at__ne=None,
        created_at__gte=start_dt,
        created_at__lt=end_dt
    )
    pr_cycle_times = []
    for pr in prs:
        cycle_time = (pr.closed_at - pr.created_at).total_seconds() / 3600
        pr_cycle_times.append(cycle_time)
    
    pr_cycle_time_median = 0
    pr_cycle_time_min = 0
    pr_cycle_time_max = 0
    pr_cycle_time_count = len(pr_cycle_times)
    
    if pr_cycle_times:
        pr_cycle_times.sort()
        pr_cycle_time_median = round(pr_cycle_times[len(pr_cycle_times) // 2], 1)
        pr_cycle_time_min = round(min(pr_cycle_times), 1)
        pr_cycle_time_max = round(max(pr_cycle_times), 1)
    
    # Calculate commit frequency (filtered by date range)
    days_diff = (end_dt - start_dt).days
    commit_frequency = {
        'avg_commits_per_day': round(total_commits / days_diff, 1) if days_diff > 0 else 0
    }
    
    # Calculate release frequency (filtered by date range)
    recent_releases = Release.objects.filter(
        repository_full_name__in=repo_full_names,
        published_at__gte=start_dt,
        published_at__lt=end_dt
    )
    months_diff = days_diff / 30
    release_frequency = {
        'releases_per_month': round(recent_releases.count() / months_diff, 1) if months_diff > 0 else 0
    }
    
    # Calculate deployment frequency (filtered by date range)
    recent_deployments = Deployment.objects.filter(
        repository_full_name__in=repo_full_names,
        created_at__gte=start_dt,
        created_at__lt=end_dt
    )
    weeks_diff = days_diff / 7
    deployment_frequency = {
        'deployments_per_week': round(recent_deployments.count() / weeks_diff, 1) if weeks_diff > 0 else 0
    }
    
    # Calculate commit change stats (filtered by date range)
    total_changes = sum(commit.additions + commit.deletions for commit in recent_commits if commit.additions and commit.deletions)
    total_files = sum(len(commit.files_changed) for commit in recent_commits if commit.files_changed)
    
    commit_change_stats = {
        'avg_total_changes': round(total_changes / total_commits, 0) if total_commits > 0 else 0,
        'avg_files_changed': round(total_files / total_commits, 1) if total_commits > 0 else 0
    }
    
    # Calculate total developers (unique emails) in date range
    unique_emails = set()
    for commit in recent_commits:
        unique_emails.add(commit.author_email)
    total_developers = len(unique_emails)
    
    # Import UnifiedMetricsService for advanced metrics
    from analytics.unified_metrics_service import UnifiedMetricsService
    import json
    
    # Calculate advanced metrics using UnifiedMetricsService
    # We'll create a custom service that aggregates across multiple repositories
    try:
        # Get all metrics for each repository and aggregate them
        all_metrics_aggregated = {}
        
        for repo in repositories:
            metrics_service = UnifiedMetricsService('repository', repo.id, start_date=start_dt, end_date=end_dt)
            repo_metrics = metrics_service.get_all_metrics()
            
            # Aggregate metrics
            for key, value in repo_metrics.items():
                if key not in all_metrics_aggregated:
                    all_metrics_aggregated[key] = value
                elif isinstance(value, dict):
                    # Merge dictionaries
                    if isinstance(all_metrics_aggregated[key], dict):
                        for sub_key, sub_value in value.items():
                            if sub_key in all_metrics_aggregated[key]:
                                if isinstance(sub_value, (int, float)) and isinstance(all_metrics_aggregated[key][sub_key], (int, float)):
                                    all_metrics_aggregated[key][sub_key] += sub_value
                                else:
                                    # For non-numeric values, keep the latest
                                    all_metrics_aggregated[key][sub_key] = sub_value
                            else:
                                all_metrics_aggregated[key][sub_key] = sub_value
                elif isinstance(value, (int, float)):
                    # Sum numeric values
                    all_metrics_aggregated[key] += value
                elif isinstance(value, list):
                    # Extend lists
                    all_metrics_aggregated[key].extend(value)
        
        # Extract specific metrics for template
        developer_activity = all_metrics_aggregated.get('developer_activity_30d', {'developers': []})
        commit_frequency_advanced = all_metrics_aggregated.get('commit_frequency', {})
        release_frequency_advanced = all_metrics_aggregated.get('release_frequency', {})
        commit_quality = all_metrics_aggregated.get('commit_quality', {})
        commit_types = all_metrics_aggregated.get('commit_type_distribution', {})
        pr_health_metrics = all_metrics_aggregated.get('pr_health_metrics', {})
        activity_heatmap = all_metrics_aggregated.get('commit_activity_by_hour', {})
        lines_added = all_metrics_aggregated.get('lines_added', 0)
        
        # Calculate global top contributors from all commits
        contributor_stats = {}
        
        # Get all commits from all repositories in the date range
        for commit in recent_commits:
            email = commit.author_email
            name = commit.author_name
            net_lines = (commit.additions or 0) - (commit.deletions or 0)
            
            if email in contributor_stats:
                # Add net_lines to existing contributor
                contributor_stats[email]['net_lines'] += net_lines
                contributor_stats[email]['commits'] += 1
            else:
                # Add new contributor
                contributor_stats[email] = {
                    'name': name,
                    'email': email,
                    'net_lines': net_lines,
                    'commits': 1
                }
        
        # Sort by net_lines and take top 10
        top_contributors = sorted(
            contributor_stats.values(), 
            key=lambda x: x['net_lines'], 
            reverse=True
        )[:10]
        
        # Calculate PR cycle time statistics
        pr_cycle_time = all_metrics_aggregated.get('pr_cycle_time', {})
        pr_cycle_time_avg = round(pr_cycle_time.get('avg_cycle_time_hours', 0), 1)
        
        # Round advanced metrics for better readability
        if release_frequency_advanced:
            release_frequency_advanced['releases_per_month'] = round(release_frequency_advanced.get('releases_per_month', 0), 1)
            release_frequency_advanced['releases_per_week'] = round(release_frequency_advanced.get('releases_per_week', 0), 1)
        
        if commit_frequency_advanced:
            commit_frequency_advanced['recent_activity_score'] = round(commit_frequency_advanced.get('recent_activity_score', 0), 1)
            commit_frequency_advanced['consistency_score'] = round(commit_frequency_advanced.get('consistency_score', 0), 1)
            commit_frequency_advanced['overall_frequency_score'] = round(commit_frequency_advanced.get('overall_frequency_score', 0), 1)
        
        if commit_quality:
            # Recalculate percentages correctly based on aggregated totals
            total_commits = commit_quality.get('total_commits', 0)
            if total_commits > 0:
                explicit_commits = commit_quality.get('explicit_commits', 0)
                generic_commits = commit_quality.get('generic_commits', 0)
                
                commit_quality['explicit_ratio'] = round((explicit_commits / total_commits * 100), 1)
                commit_quality['generic_ratio'] = round((generic_commits / total_commits * 100), 1)
            else:
                commit_quality['explicit_ratio'] = 0
                commit_quality['generic_ratio'] = 0
        
        # Round commit type ratios and recalculate statuses
        if commit_types:
            commit_types['feature_fix_ratio'] = round(commit_types.get('feature_fix_ratio', 0), 2)
            commit_types['test_feature_ratio'] = round(commit_types.get('test_feature_ratio', 0), 2)
            commit_types['chore_docs_ratio'] = round(commit_types.get('chore_docs_ratio', 0), 2)
            
            # Recalculate statuses based on aggregated ratios
            feature_fix_ratio = commit_types.get('feature_fix_ratio', 0)
            test_feature_ratio = commit_types.get('test_feature_ratio', 0)
            chore_docs_ratio = commit_types.get('chore_docs_ratio', 0)
            
            # Feature-to-Fix Ratio: feature/fix > 1 is good
            commit_types['feature_fix_status'] = 'good' if feature_fix_ratio > 1 else 'poor'
            commit_types['feature_fix_message'] = (
                'The current feature-to-fix ratio indicates a healthy focus on building new capabilities, with fewer bug fixes. This suggests the codebase is relatively stable and development is moving forward.'
                if feature_fix_ratio > 1 else
                'A low feature-to-fix ratio may indicate a high maintenance burden or recurring issues. It can suggest technical debt or instability slowing down the delivery of new value.'
            )
            
            # Test Coverage Ratio: test/feature >= 0.3 is good
            commit_types['test_feature_status'] = 'good' if test_feature_ratio >= 0.3 else 'poor'
            commit_types['test_feature_message'] = (
                'The ratio of test to feature commits reflects a strong commitment to test coverage. This improves code reliability, eases refactoring, and supports long-term maintainability.'
                if test_feature_ratio >= 0.3 else
                'A low test-to-feature ratio can be a sign of insufficient test coverage. This increases the risk of regressions and may reduce confidence in the stability of new features.'
            )
            
            # Focus Ratio: (chore + docs) / total < 0.3 is good
            commit_types['chore_docs_status'] = 'good' if chore_docs_ratio < 0.3 else 'poor'
            commit_types['chore_docs_message'] = (
                'The project shows a clear focus on product-driven development, with a balanced investment in documentation and infrastructure work.'
                if chore_docs_ratio < 0.3 else
                'A high percentage of chore and documentation commits may indicate overhead or fragmented focus. This can reduce direct impact on feature delivery and product value.'
            )
        
        if pr_health_metrics:
            # Recalculate percentages correctly based on aggregated totals
            total_prs = pr_health_metrics.get('total_prs', 0)
            if total_prs > 0:
                pr_health_metrics['merged_prs_percentage'] = round((pr_health_metrics.get('merged_prs', 0) / total_prs * 100), 1)
                pr_health_metrics['self_merged_rate'] = round((pr_health_metrics.get('self_merged_prs', 0) / total_prs * 100), 1)
                pr_health_metrics['prs_without_review_rate'] = round((pr_health_metrics.get('prs_without_review', 0) / total_prs * 100), 1)
                pr_health_metrics['old_open_prs_rate'] = round((pr_health_metrics.get('old_open_prs', 0) / total_prs * 100), 1)
                pr_health_metrics['open_prs_percentage'] = round((pr_health_metrics.get('open_prs', 0) / total_prs * 100), 1)
            else:
                pr_health_metrics['merged_prs_percentage'] = 0
                pr_health_metrics['self_merged_rate'] = 0
                pr_health_metrics['prs_without_review_rate'] = 0
                pr_health_metrics['old_open_prs_rate'] = 0
                pr_health_metrics['open_prs_percentage'] = 0
            
            # Round other metrics
            pr_health_metrics['avg_merge_time_hours'] = round(pr_health_metrics.get('avg_merge_time_hours', 0), 1)
            pr_health_metrics['median_merge_time_hours'] = round(pr_health_metrics.get('median_merge_time_hours', 0), 1)
        
        # Prepare chart data for doughnut chart
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
        
        # Calculate bubble chart data by repository
        from collections import defaultdict
        
        # Color palette for repositories
        palette = [
            {'bg': 'rgba(239, 68, 68, 0.6)', 'border': 'rgba(239, 68, 68, 1)'},   # red
            {'bg': 'rgba(59, 130, 246, 0.6)', 'border': 'rgba(59, 130, 246, 1)'}, # blue
            {'bg': 'rgba(245, 158, 11, 0.6)', 'border': 'rgba(245, 158, 11, 1)'}, # orange
            {'bg': 'rgba(139, 92, 246, 0.6)', 'border': 'rgba(139, 92, 246, 1)'}, # purple
            {'bg': 'rgba(236, 72, 153, 0.6)', 'border': 'rgba(236, 72, 153, 1)'}, # pink
            {'bg': 'rgba(34, 197, 94, 0.6)', 'border': 'rgba(34, 197, 94, 1)'},   # emerald
        ]
        
        # Group commits by repository, date and hour
        repo_bubbles = defaultdict(lambda: defaultdict(lambda: {'commits': 0, 'changes': 0}))
        
        for commit in recent_commits:
            # Get repository name
            repo_name = commit.repository_full_name.split('/')[-1] if '/' in commit.repository_full_name else commit.repository_full_name
            
            # Get local date and hour
            local_date = commit.get_authored_date_in_timezone()
            date = local_date.date()
            hour = local_date.hour
            
            key = (date, hour)
            repo_bubbles[repo_name][key]['commits'] += 1
            repo_bubbles[repo_name][key]['changes'] += (commit.additions or 0) + (commit.deletions or 0)
        
        # Create datasets for Chart.js
        chart_datasets = []
        for i, (repo_name, bubbles) in enumerate(repo_bubbles.items()):
            color = palette[i % len(palette)]
            dataset = {
                'label': repo_name,
                'data': [],
                'backgroundColor': color['bg'],
                'borderColor': color['border'],
                'borderWidth': 1
            }
            
            for (date, hour), data in bubbles.items():
                days_ago = (timezone.now().date() - date).days
                if 0 <= days_ago <= 30:  # Only show last 30 days
                    dataset['data'].append({
                        'x': days_ago,
                        'y': hour,
                        'r': min(5 + data['commits'] * 2, 20),
                        'commit_count': data['commits'],
                        'changes': data['changes']
                    })
            
            if dataset['data']:  # Only add dataset if it has data
                chart_datasets.append(dataset)
        
        activity_heatmap_data = json.dumps(chart_datasets)
        
    except Exception as e:
        # If advanced metrics calculation fails, provide empty data
        developer_activity = {'developers': []}
        commit_frequency_advanced = {}
        release_frequency_advanced = {}
        commit_quality = {'total_commits': 0, 'explicit_ratio': 0, 'generic_ratio': 0}
        commit_types = {'counts': {}}
        pr_health_metrics = {'total_prs': 0, 'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0}
        top_contributors = []
        activity_heatmap = {'hourly_data': {}, 'total_commits': 0, 'period_days': 30}
        pr_cycle_time_avg = 0
        commit_type_labels = json.dumps([])
        commit_type_values = json.dumps([])
        legend_data = []
        activity_heatmap_data = json.dumps([0] * 24)
    
    context = {
        'project': project,
        'total_commits': total_commits,
        'total_developers': total_developers,
        'total_repositories': total_repositories,
        'total_stars': total_stars,
        'total_forks': total_forks,
        'total_releases': total_releases,
        'total_deployments': total_deployments,
        'commit_frequency': commit_frequency,
        'release_frequency': release_frequency,
        'deployment_frequency': deployment_frequency,
        'commit_change_stats': commit_change_stats,
        'pr_cycle_time_median': pr_cycle_time_median,
        'pr_cycle_time_min': pr_cycle_time_min,
        'pr_cycle_time_max': pr_cycle_time_max,
        'pr_cycle_time_count': pr_cycle_time_count,
        'start_date': start_date,
        'end_date': end_date,
        
        # Advanced metrics
        'developer_activity': developer_activity,
        'commit_frequency_advanced': commit_frequency_advanced,
        'release_frequency_advanced': release_frequency_advanced,
        'commit_quality': commit_quality,
        'commit_types': commit_types,
        'pr_health_metrics': pr_health_metrics,
        'top_contributors': top_contributors,
        'activity_heatmap': activity_heatmap,
        'pr_cycle_time_avg': pr_cycle_time_avg,
        'lines_added': lines_added,
        
        # Chart data
        'commit_type_labels': commit_type_labels,
        'commit_type_values': commit_type_values,
        'commit_type_legend': legend_data,
        'doughnut_colors': doughnut_colors,
        'activity_heatmap_data': activity_heatmap_data,
    }
    return render(request, 'projects/detail.html', context)


@login_required
def project_create(request):
    """Create a new project"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        repository_ids = request.POST.getlist('repositories')
        
        if name:
            project = Project.objects.create(
                name=name,
                description=description
            )
            
            # Add selected repositories
            if repository_ids:
                repositories = Repository.objects.filter(id__in=repository_ids)
                project.repositories.set(repositories)
            
            messages.success(request, f'Project "{name}" created successfully.')
            return redirect('projects:detail', project_id=project.id)
        else:
            messages.error(request, 'Project name is required.')
    
    # Get available repositories
    repositories = Repository.objects.all().order_by('name')
    
    context = {
        'repositories': repositories,
    }
    return render(request, 'projects/create.html', context)


@login_required
def project_edit(request, project_id):
    """Edit an existing project"""
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        repository_ids = request.POST.getlist('repositories')
        
        if name:
            project.name = name
            project.description = description
            project.save()
            
            # Update repositories
            if repository_ids:
                repositories = Repository.objects.filter(id__in=repository_ids)
                project.repositories.set(repositories)
            else:
                project.repositories.clear()
            
            messages.success(request, f'Project "{name}" updated successfully.')
            return redirect('projects:detail', project_id=project.id)
        else:
            messages.error(request, 'Project name is required.')
    
    # Get available repositories
    repositories = Repository.objects.all().order_by('name')
    
    context = {
        'project': project,
        'repositories': repositories,
    }
    return render(request, 'projects/edit.html', context)


@login_required
def project_delete(request, project_id):
    """Delete a project"""
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted successfully.')
        return redirect('projects:list')
    
    context = {
        'project': project,
    }
    return render(request, 'projects/delete.html', context)
