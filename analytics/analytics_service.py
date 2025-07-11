"""
Analytics service for calculating developer metrics from commit data
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict, Counter
import re

from .models import Commit, RepositoryStats
from applications.models import Application


class AnalyticsService:
    """Service for calculating analytics from commit data"""
    
    def __init__(self, application_id: int):
        self.application_id = application_id
        self.commits = Commit.objects.filter(application_id=application_id)
    
    def get_developer_activity(self, days: int = 30) -> Dict:
        """
        Get developer activity metrics
        
        Args:
            days: Number of days to analyze (default: 30)
            
        Returns:
            Dictionary with developer activity metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_commits = self.commits.filter(authored_date__gte=cutoff_date)
        
        # Commits per developer
        commits_per_dev = {}
        for commit in recent_commits:
            dev_key = f"{commit.author_name} ({commit.author_email})"
            if dev_key not in commits_per_dev:
                commits_per_dev[dev_key] = {
                    'name': commit.author_name,
                    'email': commit.author_email,
                    'commits': 0,
                    'additions': 0,
                    'deletions': 0,
                    'files_changed': 0
                }
            
            commits_per_dev[dev_key]['commits'] += 1
            commits_per_dev[dev_key]['additions'] += commit.additions
            commits_per_dev[dev_key]['deletions'] += commit.deletions
            commits_per_dev[dev_key]['files_changed'] += len(commit.files_changed)
        
        # Sort by commits count
        sorted_devs = sorted(commits_per_dev.values(), key=lambda x: x['commits'], reverse=True)
        
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
    
    def get_code_distribution(self) -> Dict:
        """
        Get code distribution by author
        
        Returns:
            Dictionary with code distribution metrics
        """
        # Calculate total lines per author
        author_stats = defaultdict(lambda: {'additions': 0, 'deletions': 0, 'commits': 0})
        
        commits = self.commits.all()
        for commit in commits:
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
        
        # Sort by additions percentage
        distribution.sort(key=lambda x: x['additions_percentage'], reverse=True)
        
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
    
    def get_overall_stats(self) -> Dict:
        """
        Get overall application statistics
        
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
        
        # Count unique authors
        unique_authors = len(self.commits.distinct('author_email'))
        
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