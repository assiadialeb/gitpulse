"""
Management command to classify existing commits
"""
from django.core.management.base import BaseCommand
from analytics.models import Commit
from analytics.commit_classifier import classify_commit_with_ollama_fallback
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Classify existing commits by type (fix, feature, docs, etc.)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--application-id',
            type=int,
            help='Only classify commits for a specific application',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of commits to process in each batch',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        application_id = options.get('application_id')
        batch_size = options['batch_size']
        
        # Get commits to classify
        if application_id:
            commits = Commit.objects.filter(application_id=application_id)
            self.stdout.write(f"Classifying commits for application {application_id}")
        else:
            commits = Commit.objects.all()
            self.stdout.write("Classifying all commits")
        
        total_commits = commits.count()
        self.stdout.write(f"Found {total_commits} commits to classify")
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
        
        # Process in batches
        processed = 0
        updated = 0
        stats = {
            'fix': 0, 'feature': 0, 'docs': 0, 'refactor': 0,
            'test': 0, 'style': 0, 'chore': 0, 'other': 0
        }
        
        for i in range(0, total_commits, batch_size):
            batch = commits[i:i + batch_size]
            
            for commit in batch:
                processed += 1
                
                # Skip if already classified (not 'other')
                if hasattr(commit, 'commit_type') and commit.commit_type != 'other':
                    continue
                
                # Classify the commit with Ollama fallback
                commit_type = classify_commit_with_ollama_fallback(commit.message)
                stats[commit_type] += 1
                
                if not dry_run:
                    commit.commit_type = commit_type
                    commit.save()
                    updated += 1
                
                # Progress update
                if processed % 100 == 0:
                    self.stdout.write(f"Processed {processed}/{total_commits} commits...")
        
        # Show results
        self.stdout.write(self.style.SUCCESS(f"\nClassification complete!"))
        self.stdout.write(f"Total commits processed: {processed}")
        
        if not dry_run:
            self.stdout.write(f"Commits updated: {updated}")
        
        self.stdout.write("\nClassification statistics:")
        for commit_type, count in stats.items():
            if count > 0:
                percentage = (count / processed) * 100
                self.stdout.write(f"  {commit_type}: {count} ({percentage:.1f}%)")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run. Run without --dry-run to apply changes.")) 