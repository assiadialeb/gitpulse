"""
Unified metrics service for calculating analytics across repositories, projects, and developers
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional, Union
from collections import defaultdict, Counter
from django.utils import timezone as django_timezone
import re
import statistics

from .models import Commit, PullRequest, Release, Deployment, Developer, DeveloperAlias
from .cache_service import AnalyticsCacheService
from .commit_classifier import get_commit_type_stats
from .developer_grouping_service import DeveloperGroupingService


class UnifiedMetricsService:
    """
    Unified service for calculating metrics across different entities:
    - Repository (R): single repo metrics
    - Project (P): aggregated repos metrics  
    - Developer (D): single developer metrics
    """
    
    @staticmethod
    def _ensure_timezone_aware(dt):
        """Ensure a datetime is timezone-aware (UTC)"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=dt_timezone.utc)
        return dt
    
    def __init__(self, entity_type: str, entity_id: Union[int, str], start_date=None, end_date=None):
        """
        Initialize the service for a specific entity
        
        Args:
            entity_type: 'repository', 'project', or 'developer'
            entity_id: Repository ID, Project ID, or Developer ID
        """
        self.entity_type = entity_type.lower()
        self.entity_id = entity_id
        self.start_date = start_date
        self.end_date = end_date
        
        # Initialize commits queryset based on entity type
        self._setup_entity_data()
    
    def _setup_entity_data(self):
        """Setup entity-specific data and querysets"""
        if self.entity_type == 'repository':
            from repositories.models import Repository
            self.repository = Repository.objects.get(id=self.entity_id)
            self.commits = Commit.objects.filter(repository_full_name=self.repository.full_name)
            self.prs = PullRequest.objects.filter(repository_full_name=self.repository.full_name)
            self.releases = Release.objects.filter(repository_full_name=self.repository.full_name)
            self.deployments = Deployment.objects.filter(repository_full_name=self.repository.full_name)
            
        elif self.entity_type == 'project':
            from projects.models import Project
            self.project = Project.objects.get(id=self.entity_id)
            # Get all repository full names for this project
            project_repo_names = [repo.full_name for repo in self.project.repositories.all()]
            self.commits = Commit.objects.filter(repository_full_name__in=project_repo_names)
            self.prs = PullRequest.objects.filter(repository_full_name__in=project_repo_names)
            self.releases = Release.objects.filter(repository_full_name__in=project_repo_names)
            self.deployments = Deployment.objects.filter(repository_full_name__in=project_repo_names)
            
        elif self.entity_type == 'developer':
            self.developer = Developer.objects.get(id=self.entity_id)
            # Get all aliases for this developer
            aliases = DeveloperAlias.objects.filter(developer=self.developer)
            alias_emails = [alias.email for alias in aliases]
            self.commits = Commit.objects.filter(author_email__in=alias_emails)
            # For developers, PRs and releases are filtered by their commits' repos
            repo_names = set(commit.repository_full_name for commit in self.commits)
            self.prs = PullRequest.objects.filter(
                repository_full_name__in=repo_names,
                author__in=[alias.email for alias in aliases]
            )
            self.releases = Release.objects.filter(repository_full_name__in=repo_names)
            self.deployments = Deployment.objects.filter(repository_full_name__in=repo_names)
        else:
            raise ValueError(f"Invalid entity_type: {self.entity_type}")
        
        # Filtrage des commits, releases, PRs, deployments sur la plage si fournie
        self.commits = self._filter_queryset(self.commits)
        self.releases = self._filter_queryset(self.releases)
        self.prs = self._filter_queryset(self.prs)
        self.deployments = self._filter_queryset(self.deployments)
    
    def _filter_queryset(self, qs):
        if self.start_date and self.end_date:
            field = None
            if hasattr(qs, 'model'):
                model = qs.model
                if model.__name__ == 'Commit':
                    field = 'authored_date'
                elif model.__name__ == 'Release':
                    field = 'published_at'
                elif model.__name__ == 'PullRequest':
                    field = 'created_at'
                elif model.__name__ == 'Deployment':
                    field = 'created_at'
            # Fallback: test le premier objet
            if not field and hasattr(qs, 'first'):
                first = qs.first()
                if first:
                    if hasattr(first, 'authored_date'):
                        field = 'authored_date'
                    elif hasattr(first, 'published_at'):
                        field = 'published_at'
                    elif hasattr(first, 'created_at'):
                        field = 'created_at'
            if field:
                return qs.filter(**{f"{field}__gte": self.start_date, f"{field}__lte": self.end_date})
            else:
                return qs
        return qs
    
    # Basic Stats (DPR - Developers, Projects, Repositories)
    def get_total_commits(self) -> int:
        """Total Commits (DAR)"""
        return self.commits.count()
    
    def get_total_releases(self) -> int:
        """Total Releases (AR)"""
        if self.entity_type == 'developer':
            return 0  # Developers don't own releases
        return self.releases.count()
    
    def get_total_developers(self) -> int:
        """Total Developers (AR)"""
        if self.entity_type == 'developer':
            return 1  # Single developer
        
        # For both repositories and projects, use the commits we already have to count developers
        from .developer_grouping_service import DeveloperGroupingService
        grouping_service = DeveloperGroupingService()
        return grouping_service.get_all_developers_for_commits(self.commits)
    
    def get_lines_added(self) -> int:
        """Lines Added (DAR)"""
        return sum(commit.additions for commit in self.commits)
    
    def get_lines_deleted(self) -> int:
        """Lines Deleted (DAR)"""
        return sum(commit.deletions for commit in self.commits)
    
    def get_net_lines(self) -> int:
        """Net Lines Added (DAR)"""
        return self.get_lines_added() - self.get_lines_deleted()
    
    # Frequency Metrics (DAR for commits, AR for releases)
    def get_commit_frequency(self) -> Dict:
        """Commit Frequency (DAR)"""
        # Toujours utiliser self.commits filtré (déjà filtré sur la plage si fournie)
        commits_list = list(self.commits.order_by('authored_date'))
        
        if not commits_list:
            return {
                'avg_commits_per_day': 0,
                'recent_activity_score': 0,
                'consistency_score': 0,
                'overall_frequency_score': 0,
                'commits_last_30_days': 0,
                'commits_last_90_days': 0,
                'days_since_last_commit': None,
                'active_days': 0,
                'total_days': 0
            }
        
        now = datetime.now(dt_timezone.utc)
        first_commit = commits_list[0]
        last_commit = commits_list[-1]
        
        # Calculate total time span
        total_days = (last_commit.authored_date - first_commit.authored_date).days + 1
        avg_commits_per_day = len(commits_list) / total_days if total_days > 0 else 0
        
        # Calculate recent activity
        cutoff_30 = now - timedelta(days=30)
        cutoff_90 = now - timedelta(days=90)
        commits_last_30_days = sum(1 for commit in commits_list if self._ensure_timezone_aware(commit.authored_date) >= cutoff_30)
        commits_last_90_days = sum(1 for commit in commits_list if self._ensure_timezone_aware(commit.authored_date) >= cutoff_90)
        days_since_last_commit = (now - self._ensure_timezone_aware(last_commit.authored_date)).days
        
        # Calculate activity consistency
        active_days = set(commit.authored_date.date() for commit in commits_list)
        active_days_count = len(active_days)
        consistency_ratio = active_days_count / total_days if total_days > 0 else 0
        
        # Calculate scores
        recent_activity_score = min((commits_last_30_days / commits_last_90_days * 100) if commits_last_90_days > 0 else 0, 100)
        consistency_score = min(consistency_ratio * 100, 100)
        normalized_avg = min(avg_commits_per_day * 20, 100)
        overall_frequency_score = (normalized_avg * 0.3 + recent_activity_score * 0.4 + consistency_score * 0.3)
        
        return {
            'avg_commits_per_day': round(avg_commits_per_day, 2),
            'recent_activity_score': int(round(recent_activity_score)),
            'consistency_score': int(round(consistency_score)),
            'overall_frequency_score': int(round(overall_frequency_score)),
            'commits_last_30_days': commits_last_30_days,
            'commits_last_90_days': commits_last_90_days,
            'days_since_last_commit': days_since_last_commit,
            'active_days': active_days_count,
            'total_days': total_days
        }
    
    def get_release_frequency(self, period_days: int = 90) -> Dict:
        """Release Frequency (AR)"""
        if self.entity_type == 'developer':
            return {'releases_per_month': 0, 'releases_per_week': 0, 'total_releases': 0, 'period_days': period_days}
        # Si plage personnalisée, utiliser self.releases filtré, sinon period_days
        if self.start_date and self.end_date:
            releases = self.releases
            total_releases = releases.count()
            days_span = (self.end_date - self.start_date).days + 1
        else:
            cutoff = django_timezone.now() - timedelta(days=period_days)
            releases = self.releases.filter(published_at__gte=cutoff)
            total_releases = releases.count()
            days_span = period_days
        if total_releases == 0:
            return {'releases_per_month': 0, 'releases_per_week': 0, 'total_releases': 0, 'period_days': days_span}
        months = days_span / 30.44
        weeks = days_span / 7
        return {
            'releases_per_month': round(total_releases / months, 2),
            'releases_per_week': round(total_releases / weeks, 2),
            'total_releases': total_releases,
            'period_days': days_span
        }
    
    def get_pr_metrics(self) -> Dict:
        """Unified PR metrics including cycle time and health metrics (AR)"""
        if self.entity_type == 'developer':
            return {
                # Cycle time metrics
                'avg_cycle_time_hours': 0, 
                'median_cycle_time_hours': 0, 
                'min_cycle_time_hours': 0,
                'max_cycle_time_hours': 0,
                'total_prs': 0,
                # Health metrics
                'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0,
                'prs_without_review': 0, 'prs_without_review_rate': 0,
                'self_merged_prs': 0, 'self_merged_rate': 0,
                'old_open_prs': 0, 'old_open_prs_rate': 0,
                'avg_merge_time_hours': 0, 'median_merge_time_hours': 0,
                'open_prs_percentage': 0, 'merged_prs_percentage': 0
            }
        
        if self.prs.count() == 0:
            return {
                # Cycle time metrics
                'avg_cycle_time_hours': 0, 
                'median_cycle_time_hours': 0, 
                'min_cycle_time_hours': 0,
                'max_cycle_time_hours': 0,
                'total_prs': 0,
                # Health metrics
                'open_prs': 0, 'merged_prs': 0, 'closed_prs': 0,
                'prs_without_review': 0, 'prs_without_review_rate': 0,
                'self_merged_prs': 0, 'self_merged_rate': 0,
                'old_open_prs': 0, 'old_open_prs_rate': 0,
                'avg_merge_time_hours': 0, 'median_merge_time_hours': 0,
                'open_prs_percentage': 0, 'merged_prs_percentage': 0
            }
        
        # Calculate cycle times (using closed_at for consistency)
        prs_with_times = self.prs.filter(created_at__ne=None, closed_at__ne=None)
        cycle_times = []
        
        for pr in prs_with_times:
            if pr.closed_at and pr.created_at:
                cycle_time_hours = (pr.closed_at - pr.created_at).total_seconds() / 3600
                cycle_times.append(cycle_time_hours)
        
        # Calculate health metrics
        total_prs = self.prs.count()
        open_prs = self.prs.filter(state='open').count()
        merged_prs = self.prs.filter(merged_at__ne=None).count()
        closed_prs = self.prs.filter(state='closed').count()
        
        # Calculate old open PRs (open for more than 7 days)
        cutoff_date = datetime.now(dt_timezone.utc) - timedelta(days=7)
        old_open_prs = 0
        for pr in self.prs.filter(state='closed'):
            if pr.created_at and pr.closed_at:
                days_open = (pr.closed_at - pr.created_at).days
                if days_open > 7:
                    old_open_prs += 1
        
        # Calculate self-merged PRs
        self_merged_prs = 0
        for pr in self.prs.filter(merged_at__ne=None):
            if pr.merged_by and pr.author and pr.merged_by == pr.author:
                self_merged_prs += 1
        
        # Estimate PRs without review
        prs_without_review = 0
        for pr in self.prs.filter(merged_at__ne=None):
            if (pr.merged_by and pr.author and pr.merged_by == pr.author) or pr.comments_count <= 1:
                prs_without_review += 1
        
        # Calculate percentages
        open_prs_percentage = round((open_prs / total_prs * 100) if total_prs > 0 else 0, 1)
        merged_prs_percentage = round((merged_prs / total_prs * 100) if total_prs > 0 else 0, 1)
        prs_without_review_rate = round((prs_without_review / total_prs * 100) if total_prs > 0 else 0, 1)
        self_merged_rate = round((self_merged_prs / total_prs * 100) if total_prs > 0 else 0, 1)
        old_open_prs_rate = round((old_open_prs / total_prs * 100) if total_prs > 0 else 0, 1)
        
        # Calculate cycle time statistics
        avg_cycle_time = statistics.mean(cycle_times) if cycle_times else 0
        median_cycle_time = statistics.median(cycle_times) if cycle_times else 0
        min_cycle_time = min(cycle_times) if cycle_times else 0
        max_cycle_time = max(cycle_times) if cycle_times else 0
        
        return {
            # Cycle time metrics (for Release Frequency section)
            'avg_cycle_time_hours': round(avg_cycle_time, 1),
            'median_cycle_time_hours': round(median_cycle_time, 1),
            'min_cycle_time_hours': round(min_cycle_time, 1),
            'max_cycle_time_hours': round(max_cycle_time, 1),
            'total_prs': total_prs,
            'open_prs': open_prs,
            'open_prs_percentage': open_prs_percentage,
            'merged_prs': merged_prs,
            'merged_prs_percentage': merged_prs_percentage,
            'closed_prs': closed_prs,
            'prs_without_review': prs_without_review,
            'prs_without_review_rate': prs_without_review_rate,
            'self_merged_prs': self_merged_prs,
            'self_merged_rate': self_merged_rate,
            'old_open_prs': old_open_prs,
            'old_open_prs_rate': old_open_prs_rate,
            'avg_merge_time_hours': round(avg_cycle_time, 1),  # Use same value as cycle time for consistency
            'median_merge_time_hours': round(median_cycle_time, 1)
        }
    
    # Activity Metrics
    def get_developer_activity(self, days: int = 30) -> Dict:
        """Developer Activity (AR)"""
        if self.start_date and self.end_date:
            # Use the filtered commits that respect the date range
            recent_commits = self.commits
        else:
            # Fallback to days-based filtering
            cutoff_date = django_timezone.now() - timedelta(days=days)
            recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        if self.entity_type == 'developer':
            return {
                'developers': [{
                    'name': self.developer.primary_name,
                    'commits': recent_commits.count(),
                    'additions': sum(c.additions for c in recent_commits),
                    'deletions': sum(c.deletions for c in recent_commits),
                    'net_lines': sum(c.additions - c.deletions for c in recent_commits)
                }],
                'total_developers': 1
            }
        
        # For both repositories and projects, use the same logic
        # Create mapping from email to Developer
        email_to_developer = {}
        for alias in DeveloperAlias.objects():
            if alias.developer:
                email_to_developer[alias.email.lower()] = alias.developer
        
        # Aggregate by developer groups
        developer_stats = {}
        for commit in recent_commits:
            email = commit.author_email.lower()
            developer = email_to_developer.get(email)
            if developer:
                key = developer.primary_name
            else:
                key = commit.author_name
            if key not in developer_stats:
                developer_stats[key] = {'commits': 0, 'additions': 0, 'deletions': 0}
            developer_stats[key]['commits'] += 1
            developer_stats[key]['additions'] += commit.additions
            developer_stats[key]['deletions'] += commit.deletions
        
        # Format response
        developers = []
        for name, stats in developer_stats.items():
            developers.append({
                'name': name,
                'commits': stats['commits'],
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'net_lines': stats['additions'] - stats['deletions']
            })
        
        # Sort by commits desc
        developers.sort(key=lambda x: x['commits'], reverse=True)
        
        return {
            'developers': developers,
            'total_developers': len(developers)
        }
    
    # Quality Metrics (DAR)
    def get_commit_quality(self) -> Dict:
        """Commit Quality (DAR)"""
        generic_patterns = [
            r'^wip$', r'^fix$', r'^update$', r'^cleanup$', r'^refactor$',
            r'^typo$', r'^style$', r'^format$', r'^test$', r'^docs$',
            r'^chore:', r'^feat:', r'^fix:', r'^docs:', r'^style:',
            r'^refactor:', r'^test:', r'^chore\(', r'^feat\(', r'^fix\(',
            r'^update\s+\w+$', r'^fix\s+\w+$', r'^add\s+\w+$'
        ]
        
        explicit_count = 0
        generic_count = 0
        total_commits = 0
        
        for commit in self.commits:
            total_commits += 1
            message = commit.message.lower().strip()
            
            is_generic = any(re.match(pattern, message) for pattern in generic_patterns)
            if is_generic:
                generic_count += 1
            else:
                explicit_count += 1
        
        if total_commits > 0:
            explicit_ratio = (explicit_count / total_commits) * 100
            generic_ratio = (generic_count / total_commits) * 100
        else:
            explicit_ratio = 0
            generic_ratio = 0
        
        return {
            'total_commits': total_commits,
            'explicit_commits': explicit_count,
            'generic_commits': generic_count,
            'explicit_ratio': round(explicit_ratio, 1),
            'generic_ratio': round(generic_ratio, 1)
        }
    
    def get_commit_type_distribution(self) -> Dict:
        """Commit Type Distribution (DAR)"""
        return get_commit_type_stats(self.commits)
    
    # PR Cycle Time (AR) - Now uses unified method
    def get_pr_cycle_time(self) -> Dict:
        """PR Cycle Time (AR) - Returns cycle time metrics from unified PR metrics"""
        pr_metrics = self.get_pr_metrics()
        return {
            'avg_cycle_time_hours': pr_metrics['avg_cycle_time_hours'],
            'median_cycle_time_hours': pr_metrics['median_cycle_time_hours'],
            'min_cycle_time_hours': pr_metrics['min_cycle_time_hours'],
            'max_cycle_time_hours': pr_metrics['max_cycle_time_hours'],
            'total_prs': pr_metrics['total_prs']
        }
    
    # PR Health Metrics (AR) - Now uses unified method
    def get_pr_health_metrics(self) -> Dict:
        """Pull Request Health (AR) - Returns health metrics from unified PR metrics"""
        pr_metrics = self.get_pr_metrics()
        return {
            'total_prs': pr_metrics['total_prs'],
            'open_prs': pr_metrics['open_prs'],
            'open_prs_percentage': pr_metrics['open_prs_percentage'],
            'merged_prs': pr_metrics['merged_prs'],
            'merged_prs_percentage': pr_metrics['merged_prs_percentage'],
            'closed_prs': pr_metrics['closed_prs'],
            'prs_without_review': pr_metrics['prs_without_review'],
            'prs_without_review_rate': pr_metrics['prs_without_review_rate'],
            'self_merged_prs': pr_metrics['self_merged_prs'],
            'self_merged_rate': pr_metrics['self_merged_rate'],
            'old_open_prs': pr_metrics['old_open_prs'],
            'old_open_prs_rate': pr_metrics['old_open_prs_rate'],
            'avg_merge_time_hours': pr_metrics['avg_merge_time_hours'],
            'median_merge_time_hours': pr_metrics['median_merge_time_hours']
        }
    
    # Top Contributors (AR)
    def get_top_contributors(self, limit: int = 10) -> List[Dict]:
        """Top 10 Contributors by Net Lines (AR)"""
        if self.entity_type == 'developer':
            # For individual developer, return just them
            total_additions = sum(c.additions for c in self.commits)
            total_deletions = sum(c.deletions for c in self.commits)
            return [{
                'name': self.developer.primary_name,
                'additions': total_additions,
                'deletions': total_deletions,
                'net_lines': total_additions - total_deletions,
                'commits': self.commits.count()
            }]
        
        # For both repositories and projects, use the same logic
        contributor_stats = {}
        # Prepare mapping email -> Developer (if exists)
        email_to_developer = {}
        for alias in DeveloperAlias.objects():
            if alias.developer:
                email_to_developer[alias.email.lower()] = alias.developer
        
        for commit in self.commits:
            email = commit.author_email.lower()
            developer = email_to_developer.get(email)
            if developer:
                key = developer.primary_name
            else:
                key = commit.author_name
            if key not in contributor_stats:
                contributor_stats[key] = {'additions': 0, 'deletions': 0, 'commits': 0}
            contributor_stats[key]['additions'] += commit.additions
            contributor_stats[key]['deletions'] += commit.deletions
            contributor_stats[key]['commits'] += 1
        
        # Format and sort by net lines
        contributors = []
        for name, stats in contributor_stats.items():
            net_lines = stats['additions'] - stats['deletions']
            contributors.append({
                'name': name,
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'net_lines': net_lines,
                'commits': stats['commits']
            })
        
        contributors.sort(key=lambda x: x['net_lines'], reverse=True)
        return contributors[:limit]
    
    # Activity Heatmap (DAR)
    def get_commit_activity_by_hour(self, days: int = 30) -> Dict:
        """Commit Activity by Hour (DAR)"""
        if self.start_date and self.end_date:
            recent_commits = self.commits
        else:
            cutoff_date = django_timezone.now() - timedelta(days=days)
            recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Initialize hourly activity
        hourly_activity = {str(hour): 0 for hour in range(24)}
        
        for commit in recent_commits:
            hour = commit.authored_date.hour
            hourly_activity[str(hour)] += 1
        
        return {
            'hourly_data': hourly_activity,
            'total_commits': sum(hourly_activity.values()),
            'period_days': days
        }
    
    def get_bubble_chart_data(self, days: int = 30) -> Dict:
        """
        Get bubble chart data for commit activity over time and hours
        
        Args:
            days: Number of days to analyze (default: 30)
            
        Returns:
            Dictionary with bubble chart data
        """
        cutoff_date = django_timezone.now() - timedelta(days=days)
        recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Group commits by date and hour
        bubble_data = defaultdict(lambda: {'commits': 0})
        
        for commit in recent_commits:
            # Use the new timezone-aware method from the model
            local_date = commit.get_authored_date_in_timezone()
            
            date = local_date.date()
            hour = local_date.hour
            
            key = (date, hour)
            bubble_data[key]['commits'] += 1
        
        # Convert to Chart.js format
        dataset = {
            'label': self.repository.full_name if self.entity_type == 'repository' else 'Commits',
            'data': [],
            'backgroundColor': 'rgba(34, 197, 94, 0.6)',
            'borderColor': 'rgba(34, 197, 94, 1)',
            'borderWidth': 1,
            'hoverBackgroundColor': 'rgba(34, 197, 94, 0.8)',
            'hoverBorderColor': 'rgba(34, 197, 94, 1)'
        }
        
        max_commits = 0
        for (date, hour), data in bubble_data.items():
            days_ago = (django_timezone.now().date() - date).days
            dataset['data'].append({
                'x': days_ago,
                'y': hour,
                'r': min(data['commits'] * 3, 20),
                'commits': int(data['commits'])
            })
            max_commits = max(max_commits, data['commits'])
        
        return {
            'datasets': [dataset],
            'max_commits': max_commits
        }
    
    def get_commit_change_stats(self) -> Dict:
        commits = list(self.commits)
        print(f"[DEBUG] nb_commits pour commit_change_stats: {len(commits)}")
        for c in commits[:5]:
            print(f"[DEBUG] commit: sha={getattr(c, 'sha', None)}, total_changes={getattr(c, 'total_changes', None)}, files_changed={getattr(c, 'files_changed', None)}")
        if not commits:
            return {'avg_total_changes': 0, 'avg_files_changed': 0, 'nb_commits': 0}
        avg_total_changes = sum(getattr(c, 'total_changes', 0) or 0 for c in commits) / len(commits)
        avg_files_changed = sum(len(getattr(c, 'files_changed', []) or []) for c in commits) / len(commits)
        print(f'[DEBUG] avg_total_changes={avg_total_changes}, avg_files_changed={avg_files_changed}')
        return {
            'avg_total_changes': round(avg_total_changes, 2),
            'avg_files_changed': round(avg_files_changed, 2),
            'nb_commits': len(commits)
        }
    
    def get_total_deployments(self) -> int:
        """Total Deployments (AR)"""
        if self.entity_type == 'developer':
            return 0  # Developers don't own deployments
        return self.deployments.count()
    
    def get_deployment_frequency(self, period_days: int = 90) -> Dict:
        """
        Calculate deployment frequency over a period
        
        Args:
            period_days: Number of days to analyze (default: 90)
            
        Returns:
            Dictionary with deployment frequency metrics
        """
        if self.entity_type == 'developer':
            return {'total_deployments': 0, 'deployments_per_week': 0, 'period_days': period_days}
        
        # Get deployments in the specified period
        cutoff_date = django_timezone.now() - timedelta(days=period_days)
        recent_deployments = self.deployments.filter(created_at__gte=cutoff_date)
        
        total_deployments = recent_deployments.count()
        
        if total_deployments == 0:
            return {
                'total_deployments': 0,
                'deployments_per_week': 0,
                'period_days': period_days
            }
        
        # Calculate deployments per week
        weeks_in_period = period_days / 7
        deployments_per_week = total_deployments / weeks_in_period
        
        return {
            'total_deployments': total_deployments,
            'deployments_per_week': round(deployments_per_week, 2),
            'period_days': period_days
        }
    
    def get_last_deployment_date(self):
        """Get the date of the most recent deployment"""
        if self.entity_type == 'developer':
            return None  # Developers don't own deployments
        
        # Get the most recent deployment
        latest_deployment = self.deployments.order_by('-created_at').first()
        return latest_deployment.created_at if latest_deployment else None
    
    # Comprehensive metrics getter
    def get_all_metrics(self) -> Dict:
        """Get all metrics for the entity"""
        # Calculate days based on date filters
        if self.start_date and self.end_date:
            # Calculate days between start and end date
            delta = self.end_date - self.start_date
            days = delta.days + 1  # Include both start and end date
        else:
            days = 30  # Default to 30 days
        
        metrics = {
            # Basic stats
            'total_commits': self.get_total_commits(),
            'total_developers': self.get_total_developers(),
            'lines_added': self.get_lines_added(),
            'lines_deleted': self.get_lines_deleted(),
            'net_lines': self.get_net_lines(),
            
            # Frequency metrics
            'commit_frequency': self.get_commit_frequency(),
            
            # Activity metrics  
            'developer_activity_30d': self.get_developer_activity(days=days),
            'commit_activity_by_hour': self.get_commit_activity_by_hour(days=days),
            
            # Quality metrics
            'commit_quality': self.get_commit_quality(),
            'commit_type_distribution': self.get_commit_type_distribution(),
            
            # Top contributors
            'top_contributors': self.get_top_contributors(),
        }
        
        # Add metrics that are not applicable to developers
        if self.entity_type != 'developer':
            metrics.update({
                'total_releases': self.get_total_releases(),
                'release_frequency': self.get_release_frequency(),
                'pr_cycle_time': self.get_pr_cycle_time(),
                'pr_health_metrics': self.get_pr_health_metrics(),
                'total_deployments': self.get_total_deployments(),
                'deployment_frequency': self.get_deployment_frequency(),
                'last_deployment_date': self.get_last_deployment_date(),
            })
        
        # Ajout des stats de changements de commit
        metrics['commit_change_stats'] = self.get_commit_change_stats()
        return metrics 