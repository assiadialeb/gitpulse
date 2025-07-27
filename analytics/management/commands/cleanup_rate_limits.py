"""
Management command to clean up old rate limit resets and scheduled tasks
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule, Task
from datetime import datetime, timedelta, timezone as dt_timezone
from analytics.models import RateLimitReset


class Command(BaseCommand):
    help = 'Clean up old rate limit resets and scheduled tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually doing it',
        )
        parser.add_argument(
            '--older-than',
            type=int,
            default=24,
            help='Clean up items older than N hours (default: 24)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        older_than_hours = options['older_than']
        cutoff_time = datetime.now(dt_timezone.utc) - timedelta(hours=older_than_hours)

        self.stdout.write(f"Cleaning up rate limit data older than {older_than_hours} hours...")

        # Clean up old rate limit resets
        old_resets = RateLimitReset.objects.filter(
            created_at__lt=cutoff_time
        )
        
        reset_count = old_resets.count()
        if dry_run:
            self.stdout.write(f"Would delete {reset_count} old rate limit resets")
        else:
            deleted_count = old_resets.delete()
            self.stdout.write(f"Deleted {deleted_count} old rate limit resets")

        # Clean up old scheduled tasks
        old_schedules = Schedule.objects.filter(
            next_run__lt=cutoff_time,
            repeats__lt=0  # Only clean up one-time schedules
        )
        
        schedule_count = old_schedules.count()
        if dry_run:
            self.stdout.write(f"Would delete {schedule_count} old scheduled tasks")
        else:
            deleted_count = old_schedules.delete()
            self.stdout.write(f"Deleted {deleted_count} old scheduled tasks")

        # Clean up old completed tasks
        old_tasks = Task.objects.filter(
            stopped__lt=cutoff_time,
            success__isnull=False  # Only clean up completed tasks
        )
        
        task_count = old_tasks.count()
        if dry_run:
            self.stdout.write(f"Would delete {task_count} old completed tasks")
        else:
            deleted_count = old_tasks.delete()
            self.stdout.write(f"Deleted {deleted_count} old completed tasks")

        # Show current status
        self.stdout.write("\nCurrent status:")
        self.stdout.write(f"- Active rate limit resets: {RateLimitReset.objects.filter(status='pending').count()}")
        self.stdout.write(f"- Scheduled tasks: {Schedule.objects.count()}")
        self.stdout.write(f"- Recent tasks (last hour): {Task.objects.filter(started__gte=datetime.now(dt_timezone.utc) - timedelta(hours=1)).count()}")

        if not dry_run:
            self.stdout.write(self.style.SUCCESS("Cleanup completed successfully"))
        else:
            self.stdout.write(self.style.WARNING("Dry run completed - no changes made")) 