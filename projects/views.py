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
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    
    # Parse dates if provided
    from datetime import datetime, timedelta
    from django.utils import timezone
    import pytz
    if start_str and end_str:
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            end_dt = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
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
    
    # Convert the *calculated* datetime objects to strings for the template
    # This ensures the date input fields are always populated by the server
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    
    # Get all repositories in this project
    repositories = project.repositories.all()
    
    # Get repository full names for MongoDB queries
    repo_full_names = [repo.full_name for repo in repositories]
    
    # Import analytics models for additional stats
    from analytics.models import Commit, Release, PullRequest, Deployment
    
    # Initialize metrics variables
    lines_added = 0
    
    # Helper function to ensure timezone-aware datetimes
    def ensure_timezone_aware(dt):
        """Ensure a datetime is timezone-aware (UTC)"""
        if dt is None:
            return None
        if dt.tzinfo is None:
            from datetime import timezone as dt_timezone
            return dt.replace(tzinfo=dt_timezone.utc)
        return dt
    
    # Calculate commits from MongoDB
    # Check if this is "All Time" (very old start date) or specific date range
    is_all_time = False
    if start_str and end_str:
        # Check if start date is very old (more than 5 years ago) - indicates "All Time"
        from datetime import datetime, timedelta, timezone as dt_timezone
        current_year = timezone.now().year
        start_year = start_dt.year
        if current_year - start_year > 5:
            is_all_time = True
    
    if start_str and end_str and not is_all_time:
        # User specified date range - filter commits
        recent_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            authored_date__gte=start_dt,
            authored_date__lt=end_dt,
            authored_date__ne=None
        )
        total_commits = recent_commits.count()
    elif is_all_time:
        # "All Time" - show all commits for the project
        total_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            authored_date__ne=None
        ).count()

        # For recent activity calculations, still use the 30-day window
        recent_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            authored_date__gte=start_dt,
            authored_date__lt=end_dt,
            authored_date__ne=None
        )
    else:
        # No date parameters - use default date range (30 days)
        recent_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            authored_date__gte=start_dt,
            authored_date__lt=end_dt,
            authored_date__ne=None
        )
        total_commits = recent_commits.count()

    total_repositories = len(repositories)
    total_stars = sum(repo.stars for repo in repositories)
    total_forks = sum(repo.forks for repo in repositories)
    
    # Get repository full names for MongoDB queries
    repo_full_names = [repo.full_name for repo in repositories]
    
    # Import analytics models for additional stats
    from analytics.models import Commit, Release, PullRequest, Deployment
    
    # Calculate additional metrics from MongoDB
    if start_str and end_str and not is_all_time:
        # User specified date range - filter metrics
        total_releases = Release.objects.filter(
            repository_full_name__in=repo_full_names,
            published_at__gte=start_dt,
            published_at__lt=end_dt,
            published_at__ne=None
        ).count()
        
        total_deployments = Deployment.objects.filter(
            repository_full_name__in=repo_full_names,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
            created_at__ne=None
        ).count()
    elif is_all_time:
        # "All Time" - show all metrics for the project
        total_releases = Release.objects.filter(
            repository_full_name__in=repo_full_names,
            published_at__ne=None
        ).count()
        
        total_deployments = Deployment.objects.filter(
            repository_full_name__in=repo_full_names,
            created_at__ne=None
        ).count()
    else:
        # No date parameters - use default date range (30 days)
        total_releases = Release.objects.filter(
            repository_full_name__in=repo_full_names,
            published_at__gte=start_dt,
            published_at__lt=end_dt,
            published_at__ne=None
        ).count()
        
        total_deployments = Deployment.objects.filter(
            repository_full_name__in=repo_full_names,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
            created_at__ne=None
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
        published_at__lt=end_dt,
        published_at__ne=None
    )
    months_diff = days_diff / 30
    release_frequency = {
        'releases_per_month': round(recent_releases.count() / months_diff, 1) if months_diff > 0 else 0
    }
    
    # Calculate deployment frequency (filtered by date range)
    recent_deployments = Deployment.objects.filter(
        repository_full_name__in=repo_full_names,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
        created_at__ne=None
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
    
    # Calculate total developers using grouped developers
    from analytics.developer_grouping_service import DeveloperGroupingService
    
    # Get all commits for the project (filtered by date range if specified)
    if start_str and end_str and not is_all_time:
        # User specified date range - filter commits by date
        project_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            authored_date__gte=start_dt,
            authored_date__lt=end_dt,
            author_email__ne=None
        )
    elif is_all_time:
        # "All Time" - show all developers for the project
        project_commits = Commit.objects.filter(
            repository_full_name__in=repo_full_names,
            author_email__ne=None
        )
    else:
        # No date parameters - use default date range (30 days)
        project_commits = recent_commits
    
    # Use the utility method to get grouped developers count
    grouping_service = DeveloperGroupingService()
    total_developers = grouping_service.get_all_developers_for_commits(project_commits)
    
    # Import UnifiedMetricsService for advanced metrics
    from analytics.unified_metrics_service import UnifiedMetricsService
    import json
    
    # Calculate advanced metrics using UnifiedMetricsService
    # We'll create a custom service that aggregates across multiple repositories
    try:
        # Get all metrics for each repository and aggregate them
        all_metrics_aggregated = {}
        
        # Collect all commits for the project to recalculate frequency metrics
        all_project_commits = []
        
        for repo in repositories:
            metrics_service = UnifiedMetricsService('repository', repo.id, start_date=start_dt, end_date=end_dt)
            repo_metrics = metrics_service.get_all_metrics()
            
            # Collect commits for this repository
            repo_commits = Commit.objects.filter(
                repository_full_name=repo.full_name,
                authored_date__gte=start_dt,
                authored_date__lt=end_dt,
                authored_date__ne=None
            )  # Exclude commits with null dates
            all_project_commits.extend(list(repo_commits))
            
            # Aggregate metrics (but skip commit_frequency for now)
            for key, value in repo_metrics.items():
                if key == 'commit_frequency':
                    # Skip commit_frequency, we'll recalculate it for the entire project
                    continue
                    
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
        
        # Recalculate commit frequency metrics for the entire project
        if all_project_commits:
            # Sort commits by date
            all_project_commits.sort(key=lambda x: x.authored_date if x.authored_date else timezone.now())
            
            # Calculate frequency metrics for the entire project
            from datetime import datetime, timedelta
            import statistics
            
            now = timezone.now()
            first_commit = all_project_commits[0]
            last_commit = all_project_commits[-1]
            
            # Calculate total time span
            total_days = (last_commit.authored_date - first_commit.authored_date).days + 1
            
            # Calculate average commits per day
            avg_commits_per_day = len(all_project_commits) / total_days if total_days > 0 else 0
            
            # Calculate recent activity (last 30 and 90 days)
            cutoff_30 = now - timedelta(days=30)
            cutoff_90 = now - timedelta(days=90)
            
            commits_last_30_days = sum(1 for commit in all_project_commits if commit.authored_date and ensure_timezone_aware(commit.authored_date) >= cutoff_30)
            commits_last_90_days = sum(1 for commit in all_project_commits if commit.authored_date and ensure_timezone_aware(commit.authored_date) >= cutoff_90)
            
            # Calculate days since last commit
            days_since_last_commit = (now - ensure_timezone_aware(last_commit.authored_date)).days if last_commit.authored_date else 0
            
            # Calculate activity consistency
            # Group commits by day to find active days
            active_days = set()
            for commit in all_project_commits:
                if commit.authored_date:
                    active_days.add(commit.authored_date.date())
            
            active_days_count = len(active_days)
            consistency_ratio = active_days_count / total_days if total_days > 0 else 0
            
            # Calculate gaps between commits (for consistency)
            gaps = []
            for i in range(1, len(all_project_commits)):
                if all_project_commits[i].authored_date and all_project_commits[i-1].authored_date:
                    gap = (all_project_commits[i].authored_date - all_project_commits[i-1].authored_date).days
                    gaps.append(gap)
            
            avg_gap = statistics.mean(gaps) if gaps else 0
            gap_std = statistics.stdev(gaps) if len(gaps) > 1 else 0
            
            # Calculate scores (0-100 scale)
            
            # Recent activity score (0-100)
            # Based on commits in last 30 days vs 90 days
            if commits_last_90_days > 0:
                recent_activity_ratio = commits_last_30_days / commits_last_90_days
                recent_activity_score = min(recent_activity_ratio * 100, 100)
            else:
                recent_activity_score = 0
            
            # Consistency score (0-100)
            # Based on consistency ratio and gap standard deviation
            consistency_score = min(consistency_ratio * 100, 100)
            
            # Overall frequency score (0-100)
            # Weighted combination of different factors
            weights = {
                'avg_commits_per_day': 0.3,
                'recent_activity': 0.4,
                'consistency': 0.3
            }
            
            # Normalize avg_commits_per_day (0-5 commits/day = 0-100 score)
            normalized_avg = min(avg_commits_per_day * 20, 100)
            
            overall_frequency_score = (
                normalized_avg * weights['avg_commits_per_day'] +
                recent_activity_score * weights['recent_activity'] +
                consistency_score * weights['consistency']
            )
            
            # Create the aggregated commit frequency metrics
            all_metrics_aggregated['commit_frequency'] = {
                'avg_commits_per_day': round(avg_commits_per_day, 2),
                'recent_activity_score': round(recent_activity_score, 1),
                'consistency_score': round(consistency_score, 1),
                'overall_frequency_score': round(overall_frequency_score, 1),
                'commits_last_30_days': commits_last_30_days,
                'commits_last_90_days': commits_last_90_days,
                'days_since_last_commit': days_since_last_commit,
                'active_days': active_days_count,
                'total_days': total_days,
                'avg_gap_between_commits': round(avg_gap, 1),
                'gap_consistency': round(gap_std, 1)
            }
        else:
            # No commits found, provide empty metrics
            all_metrics_aggregated['commit_frequency'] = {
                'avg_commits_per_day': 0,
                'recent_activity_score': 0,
                'consistency_score': 0,
                'overall_frequency_score': 0,
                'commits_last_30_days': 0,
                'commits_last_90_days': 0,
                'days_since_last_commit': None,
                'active_days': 0,
                'total_days': 0,
                'avg_gap_between_commits': 0,
                'gap_consistency': 0
            }
        
        # Extract specific metrics for template
        commit_frequency_advanced = all_metrics_aggregated.get('commit_frequency', {})
        release_frequency_advanced = all_metrics_aggregated.get('release_frequency', {})
        commit_quality = all_metrics_aggregated.get('commit_quality', {})
        pr_health_metrics = all_metrics_aggregated.get('pr_health_metrics', {})
        activity_heatmap = all_metrics_aggregated.get('commit_activity_by_hour', {})
        lines_added = all_metrics_aggregated.get('lines_added', 0)
        
        # Calculate commit types manually from all filtered commits to ensure date filtering is respected
        from analytics.commit_classifier import get_commit_type_stats
        
        # Calculate commit types from all project commits (already filtered by date)
        commit_types = get_commit_type_stats(all_project_commits)
        
        # Calculate global top contributors from all commits using developer grouping
        contributor_stats = {}
        
        # Import developer grouping service
        from analytics.developer_grouping_service import DeveloperGroupingService
        
        # Get all commits from all repositories in the date range
        all_commits = list(recent_commits)
        
        # Get grouped developers for all repositories in this project
        # Since we don't have application_id anymore, we'll group by repository
        repo_full_names = [repo.full_name for repo in repositories]
        
        # Create mapping from email to developer group
        email_to_developer = {}
        
        # Get all developers and their aliases
        from analytics.models import Developer, DeveloperAlias
        all_developers = Developer.objects.all()
        
        for developer in all_developers:
            aliases = DeveloperAlias.objects.filter(developer=developer)
            for alias in aliases:
                email_to_developer[alias.email.lower()] = {
                    'developer_id': str(developer.id),
                    'primary_name': developer.primary_name,
                    'primary_email': developer.primary_email,
                    'confidence_score': developer.confidence_score
                }
        
        # Aggregate by developer groups
        for commit in all_commits:
            if not commit.author_email:
                continue
            email = commit.author_email.lower()
            net_lines = (commit.additions or 0) - (commit.deletions or 0)
            
            # Check if this email belongs to a developer group
            developer_info = email_to_developer.get(email)
            
            if developer_info:
                # Use developer group
                key = developer_info['developer_id']
                if key not in contributor_stats:
                    contributor_stats[key] = {
                        'name': developer_info['primary_name'],
                        'email': developer_info['primary_email'],
                        'developer_id': key,
                        'confidence_score': developer_info['confidence_score'],
                        'net_lines': 0,
                        'commits': 0,
                        'additions': 0,
                        'deletions': 0
                    }
                
                contributor_stats[key]['net_lines'] += net_lines
                contributor_stats[key]['commits'] += 1
                contributor_stats[key]['additions'] += (commit.additions or 0)
                contributor_stats[key]['deletions'] += (commit.deletions or 0)
            else:
                # Fallback to individual email (ungrouped developer)
                if email not in contributor_stats:
                    contributor_stats[email] = {
                        'name': commit.author_name,
                        'email': commit.author_email,
                        'developer_id': None,
                        'confidence_score': 100,  # Individual developer
                        'net_lines': 0,
                        'commits': 0,
                        'additions': 0,
                        'deletions': 0
                    }
                
                contributor_stats[email]['net_lines'] += net_lines
                contributor_stats[email]['commits'] += 1
                contributor_stats[email]['additions'] += (commit.additions or 0)
                contributor_stats[email]['deletions'] += (commit.deletions or 0)
        
        # Sort by net_lines and take top 10
        top_contributors = sorted(
            contributor_stats.values(), 
            key=lambda x: x['net_lines'], 
            reverse=True
        )[:10]
        
        # Calculate developer activity for the project (aggregated from all repositories)
        # Convert contributor_stats to developer_activity format
        developer_activity = {
            'developers': [],
            'total_developers': len(contributor_stats)
        }
        
        # Convert contributor_stats to developer_activity format
        for developer_id, stats in contributor_stats.items():
            developer_activity['developers'].append({
                'name': stats['name'],
                'commits': stats['commits'],
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'net_lines': stats['net_lines']
            })
        
        # Sort developers by commits (descending) for the activity display
        developer_activity['developers'].sort(key=lambda x: x['commits'], reverse=True)
        
        # Calculate PR cycle time statistics
        pr_cycle_time = all_metrics_aggregated.get('pr_cycle_time', {})
        pr_cycle_time_avg = round(pr_cycle_time.get('avg_cycle_time_hours', 0), 1)
        
        # Round advanced metrics for better readability
        if release_frequency_advanced:
            release_frequency_advanced['releases_per_month'] = round(release_frequency_advanced.get('releases_per_month', 0), 1)
            release_frequency_advanced['releases_per_week'] = round(release_frequency_advanced.get('releases_per_week', 0), 1)
        
        # No need to round commit_frequency_advanced scores as they're already calculated correctly
        
        if commit_quality:
            # Recalculate percentages correctly based on aggregated totals
            commit_quality_total = commit_quality.get('total_commits', 0)
            if commit_quality_total > 0:
                explicit_commits = commit_quality.get('explicit_commits', 0)
                generic_commits = commit_quality.get('generic_commits', 0)
                
                commit_quality['explicit_ratio'] = round((explicit_commits / commit_quality_total * 100), 1)
                commit_quality['generic_ratio'] = round((generic_commits / commit_quality_total * 100), 1)
            else:
                commit_quality['explicit_ratio'] = 0
                commit_quality['generic_ratio'] = 0
        
        # Round commit type ratios and recalculate statuses
        if commit_types:
            # Get the aggregated counts
            counts = commit_types.get('counts', {})
            commit_types_total = sum(counts.values())
            
            if commit_types_total > 0:
                # Recalculate ratios from aggregated counts
                feature_count = counts.get('feature', 0)
                fix_count = counts.get('fix', 0)
                test_count = counts.get('test', 0)
                chore_count = counts.get('chore', 0)
                docs_count = counts.get('docs', 0)
                
                # Feature-to-Fix Ratio: feature/fix > 1 is good
                if fix_count > 0:
                    feature_fix_ratio = feature_count / fix_count
                else:
                    feature_fix_ratio = feature_count if feature_count > 0 else 0
                
                # Test-to-Feature Ratio: test/feature >= 0.3 is good
                if feature_count > 0:
                    test_feature_ratio = test_count / feature_count
                else:
                    test_feature_ratio = 0
                
                # Chore+Docs Ratio: (chore + docs) / total < 0.3 is good
                chore_docs_ratio = (chore_count + docs_count) / commit_types_total
                
                # Update the ratios
                commit_types['feature_fix_ratio'] = round(feature_fix_ratio, 2)
                commit_types['test_feature_ratio'] = round(test_feature_ratio, 2)
                commit_types['chore_docs_ratio'] = round(chore_docs_ratio, 2)
                
                # Recalculate statuses based on correct ratios
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
            else:
                # No commits, set default values
                commit_types['feature_fix_ratio'] = 0
                commit_types['test_feature_ratio'] = 0
                commit_types['chore_docs_ratio'] = 0
                commit_types['feature_fix_status'] = 'poor'
                commit_types['test_feature_status'] = 'poor'
                commit_types['chore_docs_status'] = 'poor'
                commit_types['feature_fix_message'] = 'No commits available for analysis.'
                commit_types['test_feature_message'] = 'No commits available for analysis.'
                commit_types['chore_docs_message'] = 'No commits available for analysis.'
        
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
            if commit.authored_date:
                local_date = commit.get_authored_date_in_timezone()
                if local_date:
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
        doughnut_colors = {}
        activity_heatmap_data = json.dumps([0] * 24)
    
    # Generate dynamic title for developer activity based on date filters
    def get_developer_activity_title():
        if start_str and end_str and not is_all_time:
            # Custom date range - start_dt and end_dt are now always datetime objects
            start_str_formatted = start_dt.strftime('%b %d, %Y')
            end_str_formatted = end_dt.strftime('%b %d, %Y')
            return f"Developer Activity ({start_str_formatted} - {end_str_formatted})"
        elif is_all_time:
            # All time
            return "Developer Activity (All Time)"
        else:
            # Default 30 days
            return "Developer Activity (Last 30 Days)"
    
    developer_activity_title = get_developer_activity_title()

    # Calculate Codebase Size Breakdown data
    codebase_size_data = {
        'labels': [],
        'values': [],
        'colors': [],
        'legend_data': []
    }
    
    # Color palette for repositories (same as developers view)
    color_palette = [
        {'bg': 'rgba(16, 185, 129, 0.6)', 'border': 'rgba(16, 185, 129, 1)'},  # green
        {'bg': 'rgba(59, 130, 246, 0.6)', 'border': 'rgba(59, 130, 246, 1)'},  # blue
        {'bg': 'rgba(245, 158, 11, 0.6)', 'border': 'rgba(245, 158, 11, 1)'},  # orange
        {'bg': 'rgba(139, 92, 246, 0.6)', 'border': 'rgba(139, 92, 246, 1)'},  # purple
        {'bg': 'rgba(236, 72, 153, 0.6)', 'border': 'rgba(236, 72, 153, 1)'},  # pink
        {'bg': 'rgba(34, 197, 94, 0.6)', 'border': 'rgba(34, 197, 94, 1)'},    # emerald
    ]
    
    # Calculate net lines for each repository in the project
    for i, repo in enumerate(repositories):
        # Get commits for this repository within the date range
        if start_str and end_str and not is_all_time:
            # User specified date range - filter commits by date
            repo_commits = Commit.objects.filter(
                repository_full_name=repo.full_name,
                authored_date__gte=start_dt,
                authored_date__lt=end_dt,
                authored_date__ne=None
            )
        elif is_all_time:
            # "All Time" - show all commits for the repository
            repo_commits = Commit.objects.filter(
                repository_full_name=repo.full_name,
                authored_date__ne=None
            )
        else:
            # No date parameters - use default date range (30 days)
            repo_commits = Commit.objects.filter(
                repository_full_name=repo.full_name,
                authored_date__gte=start_dt,
                authored_date__lt=end_dt,
                authored_date__ne=None
            )
        
        # Calculate net lines (additions - deletions) for the filtered period
        net_lines = 0
        total_additions = 0
        total_deletions = 0
        
        for commit in repo_commits:
            additions = commit.additions or 0
            deletions = commit.deletions or 0
            total_additions += additions
            total_deletions += deletions
        
        net_lines = total_additions - total_deletions
        
        # Only include repositories with data
        if net_lines != 0:  # Changed from > 0 to != 0 to include negative values
            codebase_size_data['labels'].append(repo.name)
            codebase_size_data['values'].append(abs(net_lines))  # Use absolute value for display
            codebase_size_data['colors'].append(color_palette[i % len(color_palette)])
            codebase_size_data['legend_data'].append({
                'label': repo.name,
                'value': net_lines,  # Keep original value (can be negative)
                'color': color_palette[i % len(color_palette)]['bg']
            })
    
    # Sort data by values (largest to smallest) for proper display order
    if codebase_size_data['labels']:
        # Create list of tuples for sorting
        sorted_data = list(zip(codebase_size_data['labels'], codebase_size_data['values'], codebase_size_data['colors'], codebase_size_data['legend_data']))
        # Sort by values (ascending - smallest first, so largest appears at bottom)
        sorted_data.sort(key=lambda x: x[1], reverse=False)
        
        # Reconstruct the data in sorted order
        codebase_size_data['labels'] = [item[0] for item in sorted_data]
        codebase_size_data['values'] = [item[1] for item in sorted_data]
        codebase_size_data['colors'] = [item[2] for item in sorted_data]
        codebase_size_data['legend_data'] = [item[3] for item in sorted_data]

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
        
        # Advanced metrics
        'developer_activity': developer_activity,
        'developer_activity_title': developer_activity_title,
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
        
        # Date range parameters for template
        'start_date': start_date,
        'end_date': end_date,
        
        # Codebase Size Breakdown data
        'codebase_size_data': codebase_size_data,
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
