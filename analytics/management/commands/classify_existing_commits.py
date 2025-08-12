"""
Management command to classify existing commits
"""
from django.core.management.base import BaseCommand
from analytics.models import Commit
from analytics.commit_classifier import classify_commit_ollama
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Classify existing commits marked as "other" using Ollama LLM'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of commits to process in each batch',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of commits to process (for testing)',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        limit = options.get('limit')
        
        # Get all commits classified as "other"
        commits = list(Commit.objects(commit_type='other'))
        
        if limit:
            commits = commits[:limit]
            self.stdout.write(f"Limited to {limit} commits for testing")
        
        total_commits = len(commits)
        self.stdout.write(f"Found {total_commits} commits classified as 'other' to reclassify")
        
        if total_commits == 0:
            self.stdout.write(self.style.SUCCESS("No commits classified as 'other' found. Nothing to do."))
            return
        
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
                
                # Classify the commit with Ollama
                commit_type = classify_commit_ollama(commit.message)
                stats[commit_type] += 1
                
                if not dry_run:
                    commit.commit_type = commit_type
                    commit.save()
                    updated += 1
                
                # Progress update
                if processed % 10 == 0:
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