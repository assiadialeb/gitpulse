from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run maintenance cleanup operations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-orphaned-tasks',
            action='store_true',
            help='Skip cleaning orphaned tasks',
        )
        parser.add_argument(
            '--skip-old-tasks',
            action='store_true',
            help='Skip cleaning old completed tasks',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_orphaned_tasks = options['skip_orphaned_tasks']
        skip_old_tasks = options['skip_old_tasks']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No items will be deleted"))
        
        self.stdout.write("Starting maintenance cleanup...")
        
        # Clean orphaned tasks
        if not skip_orphaned_tasks:
            self.stdout.write("\n1. Cleaning orphaned tasks...")
            try:
                call_command('cleanup_orphaned_tasks', dry_run=dry_run)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error cleaning orphaned tasks: {e}"))
        
        # Clean old completed tasks
        if not skip_old_tasks:
            self.stdout.write("\n2. Cleaning old completed tasks...")
            try:
                self.cleanup_old_tasks(dry_run)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error cleaning old tasks: {e}"))
        
        self.stdout.write(self.style.SUCCESS("\nMaintenance cleanup completed"))

    def cleanup_old_tasks(self, dry_run):
        """Clean up old completed/failed tasks"""
        from django_q.models import Task
        from django.utils import timezone
        from datetime import timedelta
        
        # Keep tasks for 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Get old completed/failed tasks
        old_tasks = Task.objects.filter(
            stopped__lt=cutoff_date,
            success__isnull=False  # Only completed tasks (success=True or False)
        )
        
        count = old_tasks.count()
        
        if count == 0:
            self.stdout.write("  No old tasks to clean")
            return
        
        self.stdout.write(f"  Found {count} old tasks to clean")
        
        if not dry_run:
            deleted_count = old_tasks.delete()[0]
            self.stdout.write(f"  Deleted {deleted_count} old tasks")
        else:
            self.stdout.write(f"  Would delete {count} old tasks")
