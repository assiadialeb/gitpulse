"""
Management command for full commit backfill using Git local (no rate limits)
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from repositories.models import Repository
from django_q.tasks import async_task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Full commit backfill using Git local (no rate limits, no pagination)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Repository ID to backfill (default: all indexed repositories)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be backfilled without actually starting tasks',
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        dry_run = options['dry_run']
        
        # Check indexing service configuration
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'github_api')
        
        self.stdout.write(
            self.style.SUCCESS(
                "🚀 Git Local Backfill - NO rate limits, NO pagination, FULL history!"
            )
        )
        self.stdout.write(f"Current INDEXING_SERVICE: {indexing_service}")
        
        if repository_id:
            repositories = Repository.objects.filter(id=repository_id)
        else:
            repositories = Repository.objects.filter(is_indexed=True)
        
        self.stdout.write(f"Found {repositories.count()} repositories for backfill")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No tasks will be created"))
        
        total_repos = repositories.count()
        for i, repo in enumerate(repositories, 1):
            self.stdout.write(f"\n[{i}/{total_repos}] Repository: {repo.full_name} (ID: {repo.id})")
            
            # Check current commit count
            from analytics.models import Commit
            current_commits = Commit.objects(repository_full_name=repo.full_name).count()
            self.stdout.write(f"  📊 Current commits in DB: {current_commits}")
            
            if not dry_run:
                # Create the backfill task
                task_id = async_task(
                    'analytics.tasks.index_commits_intelligent_task',
                    repository_id=repo.id
                )
                self.stdout.write(f"  ✅ Backfill task created: {task_id}")
            else:
                self.stdout.write("  🔄 Would create backfill task (dry run)")
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n🎉 Started full backfill for {total_repos} repositories!"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\n📋 Would backfill {total_repos} repositories (dry run)"
                )
            )