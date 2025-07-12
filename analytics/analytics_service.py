"""
Analytics service for calculating developer metrics from commit data
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict, Counter
import re

from .models import Commit, RepositoryStats
from .developer_grouping_service import DeveloperGroupingService
from applications.models import Application


class AnalyticsService:
    """Service for calculating analytics from commit data"""
    
    def __init__(self, application_id: int):
        self.application_id = application_id
        self.commits = Commit.objects.filter(application_id=application_id)
        self.grouping_service = DeveloperGroupingService(application_id)
    
    def get_developer_activity(self, days: int = 30) -> Dict:
        """
        Get developer activity metrics with grouped developers
        
        Args:
            days: Number of days to analyze (default: 30)
            
        Returns:
            Dictionary with developer activity metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Get grouped developers
        grouped_developers = self.grouping_service.get_grouped_developers()
        
        # Create mapping from email to group
        email_to_group = {}
        for group in grouped_developers:
            for alias in group['aliases']:
                email_to_group[alias['email']] = group
        
        # Commits per developer group
        commits_per_group = {}
        for commit in recent_commits:
            # Find the group for this commit's author
            group = email_to_group.get(commit.author_email)
            
            if group:
                group_id = group['group_id']
                if group_id not in commits_per_group:
                    commits_per_group[group_id] = {
                        'name': group['primary_name'],
                        'email': group['primary_email'],
                        'group_id': group_id,
                        'confidence_score': group['confidence_score'],
                        'aliases_count': len(group['aliases']),
                        'commits': 0,
                        'additions': 0,
                        'deletions': 0,
                        'files_changed': 0,
                        'aliases': group['aliases']
                    }
                
                commits_per_group[group_id]['commits'] += 1
                commits_per_group[group_id]['additions'] += commit.additions
                commits_per_group[group_id]['deletions'] += commit.deletions
                commits_per_group[group_id]['files_changed'] += len(commit.files_changed)
            else:
                # Fallback for ungrouped developers
                dev_key = f"{commit.author_name} ({commit.author_email})"
                if dev_key not in commits_per_group:
                    commits_per_group[dev_key] = {
                        'name': commit.author_name,
                        'email': commit.author_email,
                        'group_id': None,
                        'confidence_score': 100,
                        'aliases_count': 1,
                        'commits': 0,
                        'additions': 0,
                        'deletions': 0,
                        'files_changed': 0,
                        'aliases': [{'name': commit.author_name, 'email': commit.author_email}]
                    }
                
                commits_per_group[dev_key]['commits'] += 1
                commits_per_group[dev_key]['additions'] += commit.additions
                commits_per_group[dev_key]['deletions'] += commit.deletions
                commits_per_group[dev_key]['files_changed'] += len(commit.files_changed)
        
        # Sort by name (case-insensitive), then by commits count
        sorted_devs = sorted(commits_per_group.values(), key=lambda x: (x['name'].lower(), -x['commits']))
        
        return {
            'period_days': days,
            'total_commits': recent_commits.count(),
            'developers': sorted_devs,
            'top_developer': sorted_devs[0] if sorted_devs else None
        }
    
    def get_activity_heatmap(self, days: int = 90) -> Dict:
        """
        Get activity heatmap data
        
        Args:
            days: Number of days to analyze (default: 90)
            
        Returns:
            Dictionary with heatmap data
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Group commits by date
        daily_activity = defaultdict(int)
        hourly_activity = defaultdict(int)
        
        for commit in recent_commits:
            date_key = commit.authored_date.strftime('%Y-%m-%d')
            hour_key = commit.authored_date.strftime('%H')
            
            daily_activity[date_key] += 1
            hourly_activity[hour_key] += 1
        
        # Convert to lists for frontend
        heatmap_data = []
        for date, count in sorted(daily_activity.items()):
            heatmap_data.append({
                'date': date,
                'commits': count,
                'intensity': min(count / 10, 1.0)  # Normalize to 0-1
            })
        
        return {
            'daily_activity': heatmap_data,
            'hourly_activity': dict(hourly_activity),
            'max_commits_per_day': max(daily_activity.values()) if daily_activity else 0
        }
    
    def get_bubble_chart_data(self, days: int = 30) -> Dict:
        """
        Get bubble chart data for commit activity over time and hours, split by repository
        
        Args:
            days: Number of days to analyze (default: 30)
            
        Returns:
            Dictionary with bubble chart data organized by repository
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Group commits by repository, date, and hour
        repo_bubble_data = defaultdict(lambda: defaultdict(lambda: {'commits': 0}))
        
        for commit in recent_commits:
            date = commit.authored_date.date()
            hour = commit.authored_date.hour
            repo = commit.repository_full_name
            
            key = (date, hour)
            repo_bubble_data[repo][key]['commits'] += 1
        
        # Convert to Chart.js format with separate datasets per repository
        datasets = []
        colors = [
            {'bg': 'rgba(16, 185, 129, 0.6)', 'border': 'rgba(16, 185, 129, 1)', 'hover': 'rgba(16, 185, 129, 0.8)'},  # Green
            {'bg': 'rgba(59, 130, 246, 0.6)', 'border': 'rgba(59, 130, 246, 1)', 'hover': 'rgba(59, 130, 246, 0.8)'},  # Blue
            {'bg': 'rgba(245, 158, 11, 0.6)', 'border': 'rgba(245, 158, 11, 1)', 'hover': 'rgba(245, 158, 11, 0.8)'},  # Orange
            {'bg': 'rgba(239, 68, 68, 0.6)', 'border': 'rgba(239, 68, 68, 1)', 'hover': 'rgba(239, 68, 68, 0.8)'},  # Red
            {'bg': 'rgba(139, 92, 246, 0.6)', 'border': 'rgba(139, 92, 246, 1)', 'hover': 'rgba(139, 92, 246, 0.8)'},  # Purple
            {'bg': 'rgba(236, 72, 153, 0.6)', 'border': 'rgba(236, 72, 153, 1)', 'hover': 'rgba(236, 72, 153, 0.8)'},  # Pink
        ]
        
        max_commits = 0
        for i, (repo, bubbles) in enumerate(repo_bubble_data.items()):
            color = colors[i % len(colors)]
            dataset = {
                'label': repo,
                'data': [],
                'backgroundColor': color['bg'],
                'borderColor': color['border'],
                'borderWidth': 1,
                'hoverBackgroundColor': color['hover'],
                'hoverBorderColor': color['border']
            }
            
            for (date, hour), data in bubbles.items():
                days_ago = (datetime.utcnow().date() - date).days
                dataset['data'].append({
                    'x': days_ago,
                    'y': hour,
                    'r': min(data['commits'] * 3, 20),
                    'commits': data['commits'],
                    'repository': repo
                })
                max_commits = max(max_commits, data['commits'])
            
            datasets.append(dataset)
        
        return {
            'datasets': datasets,
            'max_commits': max_commits,
            'repositories': list(repo_bubble_data.keys())
        }
    
    def get_code_distribution(self) -> Dict:
        """
        Get code distribution by author with grouped developers
        
        Returns:
            Dictionary with code distribution metrics
        """
        # Get grouped developers
        grouped_developers = self.grouping_service.get_grouped_developers()
        
        # Create mapping from email to group
        email_to_group = {}
        for group in grouped_developers:
            for alias in group['aliases']:
                email_to_group[alias['email']] = group
        
        # Calculate total lines per author group
        author_stats = defaultdict(lambda: {'additions': 0, 'deletions': 0, 'commits': 0})
        
        commits = self.commits.all()
        for commit in commits:
            # Find the group for this commit's author
            group = email_to_group.get(commit.author_email)
            
            if group:
                group_id = group['group_id']
                author_key = f"{group['primary_name']} ({group['primary_email']})"
            else:
                # Fallback for ungrouped developers
                author_key = f"{commit.author_name} ({commit.author_email})"
            
            author_stats[author_key]['additions'] += commit.additions
            author_stats[author_key]['deletions'] += commit.deletions
            author_stats[author_key]['commits'] += 1
        
        # Calculate percentages
        total_additions = sum(stats['additions'] for stats in author_stats.values())
        total_deletions = sum(stats['deletions'] for stats in author_stats.values())
        
        distribution = []
        for author, stats in author_stats.items():
            if total_additions > 0:
                additions_pct = (stats['additions'] / total_additions) * 100
            else:
                additions_pct = 0
                
            if total_deletions > 0:
                deletions_pct = (stats['deletions'] / total_deletions) * 100
            else:
                deletions_pct = 0
            
            distribution.append({
                'author': author,
                'commits': stats['commits'],
                'additions': stats['additions'],
                'deletions': stats['deletions'],
                'additions_percentage': round(additions_pct, 1),
                'deletions_percentage': round(deletions_pct, 1),
                'net_lines': stats['additions'] - stats['deletions']
            })
        
        # Sort by name (case-insensitive), then by additions percentage
        distribution.sort(key=lambda x: (x['author'].lower(), -x['additions_percentage']))
        
        return {
            'total_additions': total_additions,
            'total_deletions': total_deletions,
            'distribution': distribution
        }
    
    def get_commit_quality_metrics(self) -> Dict:
        """
        Analyze commit message quality
        
        Returns:
            Dictionary with commit quality metrics
        """
        # Define patterns for generic vs explicit messages
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
        
        commits = self.commits.all()
        for commit in commits:
            total_commits += 1
            message = commit.message.lower().strip()
            
            # Check if message matches generic patterns
            is_generic = False
            for pattern in generic_patterns:
                if re.match(pattern, message):
                    is_generic = True
                    break
            
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
        """
        Get commit type distribution statistics
        
        Returns:
            Dictionary with commit type statistics
        """
        from .commit_classifier import get_commit_type_stats
        
        commits = self.commits.all()
        return get_commit_type_stats(commits)
    
    def get_overall_stats(self) -> Dict:
        """
        Get overall application statistics with grouped developers
        
        Returns:
            Dictionary with overall stats
        """
        total_commits = self.commits.count()
        
        if total_commits == 0:
            return {
                'total_commits': 0,
                'total_authors': 0,
                'total_additions': 0,
                'total_deletions': 0,
                'first_commit_date': None,
                'last_commit_date': None,
                'avg_commits_per_day': 0
            }
        
        # Get date range
        first_commit = self.commits.order_by('authored_date').first()
        last_commit = self.commits.order_by('-authored_date').first()
        
        # Calculate total additions/deletions
        commits = self.commits.all()
        total_additions = sum(commit.additions for commit in commits)
        total_deletions = sum(commit.deletions for commit in commits)
        
        # Count unique authors using grouped developers
        grouped_developers = self.grouping_service.get_grouped_developers()
        unique_authors = len(grouped_developers)
        
        # Calculate average commits per day
        if first_commit and last_commit:
            date_range = (last_commit.authored_date - first_commit.authored_date).days + 1
            avg_commits_per_day = total_commits / date_range if date_range > 0 else 0
        else:
            avg_commits_per_day = 0
        
        return {
            'total_commits': total_commits,
            'total_authors': unique_authors,
            'total_additions': total_additions,
            'total_deletions': total_deletions,
            'first_commit_date': first_commit.authored_date if first_commit else None,
            'last_commit_date': last_commit.authored_date if last_commit else None,
            'avg_commits_per_day': round(avg_commits_per_day, 2)
        }

    def get_application_commit_frequency(self) -> Dict:
        """
        Calculate commit frequency metrics for the entire application
        
        Returns:
            Dictionary with application commit frequency metrics
        """
        from datetime import datetime, timedelta
        import statistics
        
        commits = self.commits.all()
        
        if not commits:
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
        
        # Convert to list for processing
        commits_list = list(commits.order_by('authored_date'))
        
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
        
        now = datetime.utcnow()
        first_commit = commits_list[0]
        last_commit = commits_list[-1]
        
        # Calculate total time span
        total_days = (last_commit.authored_date - first_commit.authored_date).days + 1
        
        # Calculate average commits per day
        avg_commits_per_day = len(commits_list) / total_days if total_days > 0 else 0
        
        # Calculate recent activity (last 30 and 90 days)
        cutoff_30 = now - timedelta(days=30)
        cutoff_90 = now - timedelta(days=90)
        
        commits_last_30_days = sum(1 for commit in commits_list if commit.authored_date >= cutoff_30)
        commits_last_90_days = sum(1 for commit in commits_list if commit.authored_date >= cutoff_90)
        
        # Calculate days since last commit
        days_since_last_commit = (now - last_commit.authored_date).days
        
        # Calculate activity consistency
        # Group commits by day to find active days
        active_days = set()
        for commit in commits_list:
            active_days.add(commit.authored_date.date())
        
        active_days_count = len(active_days)
        consistency_ratio = active_days_count / total_days if total_days > 0 else 0
        
        # Calculate gaps between commits (for consistency)
        gaps = []
        for i in range(1, len(commits_list)):
            gap = (commits_list[i].authored_date - commits_list[i-1].authored_date).days
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
        
        return {
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
    
    def get_grouped_developers(self) -> List[Dict]:
        """
        Get all grouped developers
        
        Returns:
            List of grouped developers
        """
        return self.grouping_service.get_grouped_developers()
    
    def get_individual_developers(self) -> List[Dict]:
        """
        Get all individual developers for manual grouping
        
        Returns:
            List of individual developers with their commit data
        """
        commits = self.commits.all()
        developers = {}
        
        for commit in commits:
            dev_key = f"{commit.author_name}|{commit.author_email}"
            if dev_key not in developers:
                developers[dev_key] = {
                    'name': commit.author_name,
                    'email': commit.author_email,
                    'first_seen': commit.authored_date,
                    'last_seen': commit.authored_date,
                    'commit_count': 0,
                    'total_additions': 0,
                    'total_deletions': 0
                }
            
            developers[dev_key]['commit_count'] += 1
            developers[dev_key]['total_additions'] += commit.additions
            developers[dev_key]['total_deletions'] += commit.deletions
            developers[dev_key]['last_seen'] = max(
                developers[dev_key]['last_seen'], 
                commit.authored_date
            )
        
        # Sort by name (case-insensitive), then by commit count
        sorted_devs = sorted(developers.values(), key=lambda x: (x['name'].lower(), -x['commit_count']))
        return sorted_devs
    
    def manually_group_developers(self, group_data: Dict) -> Dict:
        """
        Manually group developers based on user selection
        
        Args:
            group_data: Dictionary with group information
                {
                    'primary_name': str,
                    'primary_email': str,
                    'developer_ids': List[str]  # List of developer keys to group
                }
        
        Returns:
            Dictionary with grouping results
        """
        return self.grouping_service.manually_group_developers(group_data)
    
    def get_developer_detailed_stats(self, group_id: str) -> Dict:
        """
        Get detailed statistics for a specific developer group
        
        Args:
            group_id: The MongoDB ObjectId of the developer group
            
        Returns:
            Dictionary with detailed developer statistics
        """
        from .models import DeveloperGroup, DeveloperAlias
        
        # Get the developer group (global grouping, no application_id filter)
        try:
            group = DeveloperGroup.objects.get(id=group_id)
        except:
            return {
                'error': 'Developer group not found',
                'success': False
            }
        
        # Get all aliases for this group
        aliases = DeveloperAlias.objects.filter(group=group)
        
        # Get all commits for this developer group (global, from all applications)
        alias_emails = [alias.email for alias in aliases]
        from .models import Commit
        developer_commits = Commit.objects.filter(author_email__in=alias_emails)
        
        # Calculate basic stats
        total_commits = developer_commits.count()
        total_additions = sum(commit.additions for commit in developer_commits)
        total_deletions = sum(commit.deletions for commit in developer_commits)
        
        # Get date range
        first_commit = developer_commits.order_by('authored_date').first()
        last_commit = developer_commits.order_by('-authored_date').first()
        
        # Calculate activity over time (last 12 months)
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        months_data = []
        
        for i in range(12):
            month_start = now - timedelta(days=30 * (i + 1))
            month_end = now - timedelta(days=30 * i)
            
            month_commits = developer_commits.filter(
                authored_date__gte=month_start,
                authored_date__lt=month_end
            )
            
            month_additions = sum(commit.additions for commit in month_commits)
            month_deletions = sum(commit.deletions for commit in month_commits)
            
            months_data.append({
                'month': month_start.strftime('%Y-%m'),
                'commits': month_commits.count(),
                'additions': month_additions,
                'deletions': month_deletions,
                'net_lines': month_additions - month_deletions
            })
        
        # Keep newest first (no reverse needed since we build from newest to oldest)
        
        # Get most active repositories
        repo_stats = {}
        for commit in developer_commits:
            repo_name = commit.repository_full_name
            if repo_name not in repo_stats:
                repo_stats[repo_name] = {
                    'commits': 0,
                    'additions': 0,
                    'deletions': 0
                }
            
            repo_stats[repo_name]['commits'] += 1
            repo_stats[repo_name]['additions'] += commit.additions
            repo_stats[repo_name]['deletions'] += commit.deletions
        
        # Sort repositories by commit count
        sorted_repos = sorted(
            [{'name': repo, **stats} for repo, stats in repo_stats.items()],
            key=lambda x: x['commits'],
            reverse=True
        )
        
        # Get commit quality metrics for this developer
        quality_metrics = self._get_developer_commit_quality(developer_commits)
        
        return {
            'success': True,
            'group_id': group_id,
            'primary_name': group.primary_name,
            'primary_email': group.primary_email,
            'confidence_score': group.confidence_score,
            'is_auto_grouped': group.is_auto_grouped,
            'aliases': [
                {
                    'name': alias.name,
                    'email': alias.email,
                    'commit_count': alias.commit_count,
                    'first_seen': alias.first_seen,
                    'last_seen': alias.last_seen
                }
                for alias in aliases
            ],
            'total_commits': total_commits,
            'total_additions': total_additions,
            'total_deletions': total_deletions,
            'net_lines': total_additions - total_deletions,
            'first_commit_date': first_commit.authored_date if first_commit else None,
            'last_commit_date': last_commit.authored_date if last_commit else None,
            'activity_over_time': months_data,
            'top_repositories': sorted_repos[:10],  # Top 10 repositories
            'commit_quality': quality_metrics
        }
    
    def _get_developer_commit_quality(self, commits) -> Dict:
        """
        Analyze commit message quality for a specific developer
        
        Args:
            commits: QuerySet of commits for the developer
            
        Returns:
            Dictionary with commit quality metrics
        """
        # Define patterns for generic vs explicit messages
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
        
        for commit in commits:
            total_commits += 1
            message = commit.message.lower().strip()
            
            # Check if message matches generic patterns
            is_generic = False
            for pattern in generic_patterns:
                if re.match(pattern, message):
                    is_generic = True
                    break
            
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

    def get_developer_commit_frequency(self, commits) -> Dict:
        """
        Calculate commit frequency metrics for a developer
        
        Args:
            commits: QuerySet of commits for the developer
            
        Returns:
            Dictionary with commit frequency metrics
        """
        from datetime import datetime, timedelta
        import statistics
        
        if not commits:
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
        
        # Convert to list for processing
        commits_list = list(commits.order_by('authored_date'))
        
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
        
        now = datetime.utcnow()
        first_commit = commits_list[0]
        last_commit = commits_list[-1]
        
        # Calculate total time span
        total_days = (last_commit.authored_date - first_commit.authored_date).days + 1
        
        # Calculate average commits per day
        avg_commits_per_day = len(commits_list) / total_days if total_days > 0 else 0
        
        # Calculate recent activity (last 30 and 90 days)
        cutoff_30 = now - timedelta(days=30)
        cutoff_90 = now - timedelta(days=90)
        
        commits_last_30_days = sum(1 for commit in commits_list if commit.authored_date >= cutoff_30)
        commits_last_90_days = sum(1 for commit in commits_list if commit.authored_date >= cutoff_90)
        
        # Calculate days since last commit
        days_since_last_commit = (now - last_commit.authored_date).days
        
        # Calculate activity consistency
        # Group commits by day to find active days
        active_days = set()
        for commit in commits_list:
            active_days.add(commit.authored_date.date())
        
        active_days_count = len(active_days)
        consistency_ratio = active_days_count / total_days if total_days > 0 else 0
        
        # Calculate gaps between commits (for consistency)
        gaps = []
        for i in range(1, len(commits_list)):
            gap = (commits_list[i].authored_date - commits_list[i-1].authored_date).days
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
        
        return {
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