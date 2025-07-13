"""
Quality analysis service for commits
"""
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any
from pymongo import MongoClient
import pymongo

from .models import Commit

logger = logging.getLogger(__name__)


class QualityAnalysisService:
    """Service for analyzing commit quality during indexing"""
    
    def __init__(self):
        # Connect to MongoDB
        self.client = MongoClient('localhost', 27017)
        self.db = self.client['gitpulse']
        
        # Collection for quality metrics
        self.quality_collection = self.db['developer_quality_metrics']
        
        # Create indexes
        self.quality_collection.create_index([("commit_sha", pymongo.ASCENDING)])
        self.quality_collection.create_index([("developer_email", pymongo.ASCENDING)])
        self.quality_collection.create_index([("repository", pymongo.ASCENDING)])
        self.quality_collection.create_index([("analysis_date", pymongo.DESCENDING)])
    
    def analyze_commit_quality(self, commit: Commit) -> Dict[str, Any]:
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
    
    def _calculate_code_quality_score(self, metrics: Dict[str, Any]) -> int:
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
    
    def _calculate_impact_score(self, metrics: Dict[str, Any]) -> int:
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
    
    def _calculate_complexity_score(self, metrics: Dict[str, Any]) -> int:
        """Calculate complexity score (0-100)"""
        score = 30  # Base score for any commit
        
        # Based on commit type (very generous)
        type_scores = {
            'feature': 40,
            'fix': 35,
            'refactor': 30,
            'test': 25,
            'docs': 15,
            'style': 10,
            'chore': 10,
            'other': 20
        }
        score += type_scores.get(metrics['commit_type'], 20)
        
        # Based on file types (very generous)
        if metrics['code_files'] > 0:
            score += 25
        if metrics['test_files'] > 0:
            score += 15
        
        # Based on changes (very generous)
        if metrics['total_changes'] > 15:
            score += 20
        elif metrics['total_changes'] > 5:
            score += 15
        elif metrics['total_changes'] > 1:
            score += 10
        
        return max(0, min(100, score))
    
    def _detect_suspicious_patterns(self, metrics: Dict[str, Any]) -> list:
        """Detect suspicious patterns in commit"""
        patterns = []
        
        # Micro commit (very small changes)
        if metrics['total_changes'] <= 2:
            patterns.append('micro_commit')
        
        # No ticket reference
        if not metrics['message_has_ticket']:
            patterns.append('no_ticket_reference')
        
        # Only documentation
        if metrics['is_documentation_only']:
            patterns.append('documentation_only')
        
        # Only configuration
        if metrics['is_config_only']:
            patterns.append('configuration_only')
        
        # Formatting only
        if metrics['message_has_format'] and metrics['total_changes'] <= 5:
            patterns.append('formatting_only')
        
        # Typo fixes (not suspicious, just informational)
        if metrics['message_has_typo_fix']:
            patterns.append('typo_fix')
        
        return patterns
    
    def store_commit_quality(self, commit: Commit) -> bool:
        """Analyze and store quality metrics for a commit"""
        try:
            # Analyze commit quality
            quality_metrics = self.analyze_commit_quality(commit)
            
            # Store in MongoDB
            self.quality_collection.update_one(
                {'commit_sha': commit.sha},
                {'$set': quality_metrics},
                upsert=True
            )
            
            logger.info(f"Stored quality metrics for commit {commit.sha}")
            return True
            
        except Exception as e:
            logger.error(f"Error analyzing commit {commit.sha}: {e}")
            return False
    
    def analyze_commits_for_application(self, application_id: int) -> int:
        """Analyze all commits for an application"""
        try:
            commits = Commit.objects.filter(application_id=application_id)
            processed = 0
            
            for commit in commits:
                if self.store_commit_quality(commit):
                    processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"Processed {processed} commits for application {application_id}")
            
            logger.info(f"Completed quality analysis for application {application_id}: {processed} commits")
            return processed
            
        except Exception as e:
            logger.error(f"Error analyzing commits for application {application_id}: {e}")
            return 0 