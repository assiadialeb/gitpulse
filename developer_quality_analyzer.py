#!/usr/bin/env python3
"""
Developer Quality Analyzer
Analyzes commit patterns to detect "surface developers" who do minimal real work
"""
import os
import sys
import django
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import re
from typing import Optional

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analytics.models import Commit, DeveloperGroup, DeveloperAlias
from pymongo import MongoClient
import pymongo


class DeveloperQualityAnalyzer:
    """Analyzes developer quality based on commit patterns"""
    
    def __init__(self):
        # Connect to MongoDB
        self.client = MongoClient('localhost', 27017)
        self.db = self.client['gitpulse']
        
        # Collection for quality metrics
        self.quality_collection = self.db['developer_quality_metrics']
        
        # Create indexes
        self.quality_collection.create_index([("developer_id", pymongo.ASCENDING)])
        self.quality_collection.create_index([("commit_sha", pymongo.ASCENDING)])
        self.quality_collection.create_index([("analysis_date", pymongo.DESCENDING)])
    
    def analyze_commit_quality(self, commit):
        """Analyze a single commit and return quality metrics"""
        
        # Get commit data
        message = commit.message.lower()
        commit_type = commit.commit_type
        additions = commit.additions
        deletions = commit.deletions
        total_changes = commit.total_changes
        files_changed = commit.files_changed
        
        # Initialize metrics
        metrics = {
            'commit_sha': commit.sha,
            'developer_email': commit.author_email,
            'developer_name': commit.author_name,
            'repository': commit.repository_full_name,
            'application_id': commit.application_id,
            'commit_date': commit.authored_date,
            'analysis_date': datetime.now(timezone.utc),
            
            # Basic commit info
            'commit_type': commit_type,
            'additions': additions,
            'deletions': deletions,
            'total_changes': total_changes,
            'files_count': len(files_changed),
            
            # Quality scores (0-100)
            'code_quality_score': 0,
            'impact_score': 0,
            'complexity_score': 0,
            'suspicious_patterns': [],
            
            # Pattern detection
            'is_documentation_only': False,
            'is_config_only': False,
            'is_formatting_only': False,
            'is_dependency_only': False,
            'is_minor_fix': False,
            'is_real_code': False,
            
            # File analysis
            'code_files': 0,
            'config_files': 0,
            'doc_files': 0,
            'test_files': 0,
            'other_files': 0,
            
            # Message analysis
            'message_length': len(message),
            'message_has_ticket': bool(re.search(r'#[0-9]+', message)),
            'message_has_typo_fix': bool(re.search(r'typo|spell|grammar', message)),
            'message_has_format': bool(re.search(r'format|style|indent|whitespace', message)),
        }
        
        # Analyze file types
        for file_change in files_changed:
            filename = file_change.filename.lower()
            
            # Code files
            if any(ext in filename for ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.php', '.rb']):
                metrics['code_files'] += 1
                metrics['is_real_code'] = True
            
            # Test files
            elif any(pattern in filename for pattern in ['test', 'spec', 'specs', '_test.', '.test.']):
                metrics['test_files'] += 1
                metrics['is_real_code'] = True
            
            # Documentation files
            elif any(ext in filename for ext in ['.md', '.txt', '.rst', '.adoc', 'readme', 'docs/', 'documentation/']):
                metrics['doc_files'] += 1
            
            # Configuration files
            elif any(ext in filename for ext in ['.json', '.yaml', '.yml', '.toml', '.ini', '.conf', '.config', 'package.json', 'requirements.txt', 'pom.xml', 'build.gradle']):
                metrics['config_files'] += 1
            
            # Other files
            else:
                metrics['other_files'] += 1
        
        # Determine if commit is only documentation or config (after analyzing all files)
        if metrics['doc_files'] > 0 and metrics['code_files'] == 0 and metrics['test_files'] == 0:
            metrics['is_documentation_only'] = True
        
        if metrics['config_files'] > 0 and metrics['code_files'] == 0 and metrics['test_files'] == 0:
            metrics['is_config_only'] = True
        
        # Calculate quality scores
        metrics['code_quality_score'] = self._calculate_code_quality_score(metrics)
        metrics['impact_score'] = self._calculate_impact_score(metrics)
        metrics['complexity_score'] = self._calculate_complexity_score(metrics)
        
        # Detect suspicious patterns
        metrics['suspicious_patterns'] = self._detect_suspicious_patterns(metrics)
        
        return metrics
    
    def _calculate_code_quality_score(self, metrics):
        """Calculate code quality score (0-100)"""
        score = 50  # Base score for any commit
        
        # Bonus for real code (very generous)
        if metrics['is_real_code']:
            score += 40
        
        # Bonus for tests (generous)
        if metrics['test_files'] > 0:
            score += 20
        
        # Small penalty for only documentation/config (very reduced)
        if metrics['is_documentation_only'] and not metrics['is_real_code']:
            score -= 5
        
        if metrics['is_config_only'] and not metrics['is_real_code']:
            score -= 3
        
        # Small penalty for formatting only (very reduced)
        if metrics['is_formatting_only']:
            score -= 2
        
        # Bonus for any changes (very generous)
        if metrics['total_changes'] > 10:
            score += 15
        elif metrics['total_changes'] > 2:
            score += 10
        
        return max(0, min(100, score))
    
    def _calculate_impact_score(self, metrics):
        """Calculate impact score (0-100)"""
        score = 40  # Base score for any commit
        
        # Based on number of files changed (very generous)
        if metrics['files_count'] > 3:
            score += 30
        elif metrics['files_count'] > 1:
            score += 20
        
        # Based on lines changed (very generous)
        if metrics['total_changes'] > 20:
            score += 40
        elif metrics['total_changes'] > 10:
            score += 30
        elif metrics['total_changes'] > 5:
            score += 20
        elif metrics['total_changes'] > 1:
            score += 15
        
        # Small penalty for very small changes (very reduced)
        if metrics['total_changes'] <= 1:
            score -= 5
        
        return max(0, min(100, score))
    
    def _calculate_complexity_score(self, metrics):
        """Calculate complexity score (0-100)"""
        score = 30  # Base score for any commit
        
        # Based on commit type (very generous)
        type_scores = {
            'feature': 50,
            'fix': 45,
            'refactor': 40,
            'test': 35,
            'docs': 25,
            'style': 20,
            'chore': 15,
            'other': 30
        }
        score += type_scores.get(metrics['commit_type'], 30)
        
        # Based on file types (very generous)
        score += metrics['code_files'] * 15
        score += metrics['test_files'] * 10
        
        # Small penalty for only config/docs (very reduced)
        if metrics['config_files'] > 0 and metrics['code_files'] == 0:
            score -= 3
        
        if metrics['doc_files'] > 0 and metrics['code_files'] == 0:
            score -= 2
        
        return max(0, min(100, score))
    
    def _detect_suspicious_patterns(self, metrics):
        """Detect suspicious patterns in the commit"""
        patterns = []
        
        # Only documentation changes (only if no real code AND very small)
        if metrics['is_documentation_only'] and not metrics['is_real_code'] and metrics['total_changes'] <= 1:
            patterns.append('documentation_only')
        
        # Only configuration changes (only if no real code AND very small)
        if metrics['is_config_only'] and not metrics['is_real_code'] and metrics['total_changes'] <= 1:
            patterns.append('configuration_only')
        
        # Very small changes (only if no real code)
        if metrics['total_changes'] <= 1 and not metrics['is_real_code']:
            patterns.append('micro_commit')
        
        # Typo fixes (only if very small)
        if metrics['message_has_typo_fix'] and metrics['total_changes'] <= 1:
            patterns.append('typo_fix')
        
        # Formatting only (only if very small)
        if metrics['message_has_format'] and metrics['total_changes'] <= 1:
            patterns.append('formatting_only')
        
        # Many small files (only if suspicious pattern)
        if metrics['files_count'] > 10 and metrics['total_changes'] < 5:
            patterns.append('many_small_changes')
        
        # No ticket reference (for display only, doesn't count as suspicious)
        if not metrics['message_has_ticket'] and metrics['total_changes'] > 5:
            patterns.append('no_ticket_reference')
        
        return patterns
    
    def analyze_all_commits(self, application_id=None, days_back: Optional[int] = 30):
        """Analyze all commits and store metrics"""
        
        # Get commits to analyze
        query = {}
        if application_id:
            query['application_id'] = application_id
        
        if days_back is not None:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            query['authored_date__gte'] = cutoff_date
        
        commits = Commit.objects.filter(**query).order_by('-authored_date')
        
        print(f"Analyzing {commits.count()} commits...")
        
        processed = 0
        for commit in commits:
            try:
                # Analyze commit
                metrics = self.analyze_commit_quality(commit)
                
                # Store in MongoDB
                self.quality_collection.update_one(
                    {'commit_sha': commit.sha},
                    {'$set': metrics},
                    upsert=True
                )
                
                processed += 1
                if processed % 100 == 0:
                    print(f"Processed {processed} commits...")
                    
            except Exception as e:
                print(f"Error analyzing commit {commit.sha}: {e}")
                continue
        
        print(f"Analysis complete! Processed {processed} commits.")
        return processed
    
    def get_developer_summary(self, developer_email, days_back=30):
        """Get quality summary for a specific developer"""
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        pipeline = [
            {
                '$match': {
                    'developer_email': developer_email,
                    'commit_date': {'$gte': cutoff_date}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total_commits': {'$sum': 1},
                    'avg_code_quality': {'$avg': '$code_quality_score'},
                    'avg_impact': {'$avg': '$impact_score'},
                    'avg_complexity': {'$avg': '$complexity_score'},
                    'total_additions': {'$sum': '$additions'},
                    'total_deletions': {'$sum': '$deletions'},
                    'total_files': {'$sum': '$files_count'},
                    'code_files': {'$sum': '$code_files'},
                    'test_files': {'$sum': '$test_files'},
                    'doc_files': {'$sum': '$doc_files'},
                    'config_files': {'$sum': '$config_files'},
                    'suspicious_commits': {
                        '$sum': {'$cond': [{'$gt': [{'$size': '$suspicious_patterns'}, 0]}, 1, 0]}
                    }
                }
            }
        ]
        
        result = list(self.quality_collection.aggregate(pipeline))
        return result[0] if result else None
    
    def get_suspicious_developers(self, application_id=None, days_back: Optional[int] = 30, min_commits=5):
        """Get list of developers with suspicious patterns"""
        
        match_stage = {}
        if days_back is not None:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            match_stage['commit_date'] = {'$gte': cutoff_date}
        if application_id:
            match_stage['application_id'] = application_id
        
        pipeline = [
            {'$match': match_stage},
            {
                '$group': {
                    '_id': '$developer_email',
                    'developer_name': {'$first': '$developer_name'},
                    'total_commits': {'$sum': 1},
                    'avg_code_quality': {'$avg': '$code_quality_score'},
                    'avg_impact': {'$avg': '$impact_score'},
                    'avg_complexity': {'$avg': '$complexity_score'},
                    'suspicious_commits': {
                        '$sum': {'$cond': [{'$gt': [{'$size': '$suspicious_patterns'}, 0]}, 1, 0]}
                    },
                    'doc_only_commits': {
                        '$sum': {'$cond': ['$is_documentation_only', 1, 0]}
                    },
                    'config_only_commits': {
                        '$sum': {'$cond': ['$is_config_only', 1, 0]}
                    },
                    'real_code_commits': {
                        '$sum': {'$cond': ['$is_real_code', 1, 0]}
                    }
                }
            },
            {
                '$match': {
                    'total_commits': {'$gte': min_commits}
                }
            },
            {
                '$addFields': {
                    'suspicious_ratio': {
                        '$divide': ['$suspicious_commits', '$total_commits']
                    },
                    'real_code_ratio': {
                        '$divide': ['$real_code_commits', '$total_commits']
                    }
                }
            },
            {
                '$sort': {
                    'suspicious_ratio': -1,
                    'avg_code_quality': 1
                }
            }
        ]
        
        return list(self.quality_collection.aggregate(pipeline))


def main():
    """Main function to run the analysis"""
    
    analyzer = DeveloperQualityAnalyzer()
    
    # Analyze all commits (no time limit)
    print("Starting developer quality analysis...")
    processed = analyzer.analyze_all_commits(days_back=None)
    
    # Get suspicious developers (no time limit)
    print("\nFinding suspicious developers...")
    suspicious_devs = analyzer.get_suspicious_developers(days_back=None, min_commits=5)
    
    print(f"\nFound {len(suspicious_devs)} developers with suspicious patterns:")
    print("=" * 80)
    
    for i, dev in enumerate(suspicious_devs[:10], 1):  # Show top 10
        print(f"{i}. {dev['developer_name']} ({dev['_id']})")
        print(f"   Commits: {dev['total_commits']}")
        print(f"   Suspicious ratio: {dev['suspicious_ratio']:.1%}")
        print(f"   Real code ratio: {dev['real_code_ratio']:.1%}")
        print(f"   Avg code quality: {dev['avg_code_quality']:.1f}/100")
        print(f"   Doc-only commits: {dev['doc_only_commits']}")
        print(f"   Config-only commits: {dev['config_only_commits']}")
        print(f"   Real code commits: {dev['real_code_commits']}")
        print("-" * 40)
    
    print(f"\nAnalysis complete! Check MongoDB collection 'developer_quality_metrics' for detailed data.")


if __name__ == "__main__":
    main() 