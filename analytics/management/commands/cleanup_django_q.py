"""
Management command to completely clean up Django-Q queue and schedules
"""
from django.core.management.base import BaseCommand
from django_q.models import Task, Schedule
from django_q.cluster import Cluster


class Command(BaseCommand):
    help = 'Completely clean up Django-Q queue and schedules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--restart-cluster',
            action='store_true',
            help='Restart Django-Q cluster after cleanup',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        restart_cluster = options['restart_cluster']
        
        self.stdout.write('🧹 Starting comprehensive Django-Q cleanup...')
        
        # 1. Clean up old function references
        old_functions = [
            'analytics.tasks.release_indexing_all_apps_task',
            'analytics.tasks.daily_indexing_all_apps_task',
            'analytics.tasks.quality_analysis_all_apps_task',
            'analytics.tasks.manual_indexing_task',
        ]
        
        # 2. Find and report old tasks
        old_tasks = Task.objects.filter(func__in=old_functions)
        old_schedules = Schedule.objects.filter(func__in=old_functions)
        
        self.stdout.write(f'Found {old_tasks.count()} old tasks and {old_schedules.count()} old schedules')
        
        if dry_run:
            self.stdout.write('📋 DRY RUN - Would delete:')
            for task in old_tasks:
                self.stdout.write(f'  - Task: {task.func} (ID: {task.id})')
            for schedule in old_schedules:
                self.stdout.write(f'  - Schedule: {schedule.name} -> {schedule.func}')
            return
        
        # 3. Delete old tasks and schedules
        if old_tasks.exists():
            old_tasks.delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {old_tasks.count()} old tasks'))
        
        if old_schedules.exists():
            old_schedules.delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {old_schedules.count()} old schedules'))
        
        # 4. Clean up any failed tasks
        failed_tasks = Task.objects.filter(success=False)
        if failed_tasks.exists():
            failed_count = failed_tasks.count()
            failed_tasks.delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {failed_count} failed tasks'))
        
        # 5. Show current status
        total_tasks = Task.objects.count()
        total_schedules = Schedule.objects.count()
        
        self.stdout.write('')
        self.stdout.write('📊 Current Status:')
        self.stdout.write(f'  - Tasks in queue: {total_tasks}')
        self.stdout.write(f'  - Scheduled tasks: {total_schedules}')
        
        # 6. Show current schedules
        if total_schedules > 0:
            self.stdout.write('')
            self.stdout.write('📅 Current Schedules:')
            schedules = Schedule.objects.all()
            for schedule in schedules:
                status = '✅ Active' if schedule.next_run else '❌ Inactive'
                self.stdout.write(f'  - {schedule.name}: {schedule.func} | {status}')
        
        # 7. Restart cluster if requested
        if restart_cluster:
            self.stdout.write('')
            self.stdout.write('🔄 Restarting Django-Q cluster...')
            try:
                cluster = Cluster()
                cluster.stop()
                cluster.start()
                self.stdout.write(self.style.SUCCESS('✅ Cluster restarted'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Failed to restart cluster: {e}'))
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🎉 Cleanup completed!'))
        
        if total_tasks == 0 and total_schedules > 0:
            self.stdout.write('💡 Tip: Run "python manage.py qcluster" to start the worker cluster') 