"""
Management command to clean up old tasks from Django-Q queue
"""
from django.core.management.base import BaseCommand
from django_q.models import Task, Schedule


class Command(BaseCommand):
    help = 'Clean up old tasks from Django-Q queue'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--failed-only',
            action='store_true',
            help='Only clean up failed tasks',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        failed_only = options['failed_only']
        
        # Clean up old function references
        old_functions = [
            'analytics.tasks.release_indexing_all_apps_task',
            'analytics.tasks.daily_indexing_all_apps_task',
            'analytics.tasks.quality_analysis_all_apps_task',
            'analytics.tasks.manual_indexing_task',  # Old signature
        ]
        
        # Find tasks with old function names
        old_tasks = Task.objects.filter(func__in=old_functions)
        
        if failed_only:
            old_tasks = old_tasks.filter(success=False)
        
        if not old_tasks.exists():
            self.stdout.write(self.style.SUCCESS('No old tasks found to clean up.'))
            return
        
        self.stdout.write(f'Found {old_tasks.count()} old tasks to clean up:')
        self.stdout.write('=' * 60)
        
        for task in old_tasks:
            status = '❌ Failed' if not task.success else '✅ Success'
            self.stdout.write(f'- {task.func} ({status})')
        
        self.stdout.write('=' * 60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No tasks were actually deleted. Use without --dry-run to delete.')
            )
            return
        
        # Delete old tasks
        deleted_count = old_tasks.count()
        old_tasks.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {deleted_count} old tasks.')
        )
        
        # Also clean up any old schedules that might reference old functions
        old_schedules = Schedule.objects.filter(func__in=old_functions)
        if old_schedules.exists():
            schedule_count = old_schedules.count()
            old_schedules.delete()
            self.stdout.write(
                self.style.SUCCESS(f'Also deleted {schedule_count} old schedules.')
            )
        
        # Show current queue status
        total_tasks = Task.objects.count()
        failed_tasks = Task.objects.filter(success=False).count()
        
        self.stdout.write('')
        self.stdout.write('📊 Current Queue Status:')
        self.stdout.write(f'- Total tasks: {total_tasks}')
        self.stdout.write(f'- Failed tasks: {failed_tasks}')
        
        if failed_tasks > 0:
            self.stdout.write(
                self.style.WARNING(f'⚠️  {failed_tasks} failed tasks remaining. Consider running with --failed-only to clean them up.')
            ) 