from django.core.management.base import BaseCommand
from django_q.models import Schedule, Task
from repositories.models import Repository
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up orphaned tasks that reference non-existent repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually deleting',
        )
        parser.add_argument(
            '--task-types',
            nargs='+',
            choices=['schedule', 'task', 'all'],
            default=['all'],
            help='Types of orphaned items to clean (default: all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        task_types = options['task_types']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No items will be deleted"))
        
        self.stdout.write("Cleaning up orphaned tasks...")
        
        # Get all repository IDs that exist
        existing_repo_ids = set(Repository.objects.values_list('id', flat=True))
        
        cleaned_count = 0
        
        if 'schedule' in task_types or 'all' in task_types:
            cleaned_count += self.cleanup_orphaned_schedules(existing_repo_ids, dry_run)
        
        if 'task' in task_types or 'all' in task_types:
            cleaned_count += self.cleanup_orphaned_tasks(existing_repo_ids, dry_run)
        
        self.stdout.write(
            self.style.SUCCESS(f"Cleanup completed: {cleaned_count} orphaned items {'would be ' if dry_run else ''}deleted")
        )

    def cleanup_orphaned_schedules(self, existing_repo_ids, dry_run):
        """Clean up orphaned scheduled tasks"""
        cleaned_count = 0
        
        # Get all schedules that reference repositories
        schedules = Schedule.objects.filter(
            func__in=[
                'analytics.tasks.index_commits_intelligent_task',
                'analytics.tasks.index_pullrequests_intelligent_task',
                'analytics.tasks.index_releases_intelligent_task',
                'analytics.tasks.index_deployments_intelligent_task',
                'analytics.tasks.index_codeql_intelligent_task',
                'analytics.tasks.index_commits_git_local_task',
                'analytics.tasks.generate_sbom_task',
            ]
        )
        
        for schedule in schedules:
            try:
                # Extract repository_id from args
                if schedule.args and len(schedule.args) > 0:
                    repo_id = schedule.args[0]
                    if isinstance(repo_id, list):
                        repo_id = repo_id[0]
                    
                    repo_id = int(repo_id)
                    
                    if repo_id not in existing_repo_ids:
                        self.stdout.write(f"  Orphaned schedule: {schedule.name} (repo_id: {repo_id})")
                        if not dry_run:
                            schedule.delete()
                        cleaned_count += 1
                        
            except (ValueError, TypeError, IndexError) as e:
                # Invalid args format, clean up corrupted schedule
                self.stdout.write(f"  Corrupted schedule: {schedule.name} (error: {e})")
                if not dry_run:
                    schedule.delete()
                cleaned_count += 1
        
        return cleaned_count

    def cleanup_orphaned_tasks(self, existing_repo_ids, dry_run):
        """Clean up orphaned completed/failed tasks"""
        cleaned_count = 0
        
        # Get all tasks that reference repositories
        tasks = Task.objects.filter(
            func__in=[
                'analytics.tasks.index_commits_intelligent_task',
                'analytics.tasks.index_pullrequests_intelligent_task',
                'analytics.tasks.index_releases_intelligent_task',
                'analytics.tasks.index_deployments_intelligent_task',
                'analytics.tasks.index_codeql_intelligent_task',
                'analytics.tasks.index_commits_git_local_task',
                'analytics.tasks.generate_sbom_task',
            ]
        )
        
        for task in tasks:
            try:
                # Extract repository_id from args
                if task.args and len(task.args) > 0:
                    repo_id = task.args[0]
                    if isinstance(repo_id, list):
                        repo_id = repo_id[0]
                    
                    repo_id = int(repo_id)
                    
                    if repo_id not in existing_repo_ids:
                        self.stdout.write(f"  Orphaned task: {task.id} (repo_id: {repo_id}, status: {task.success})")
                        if not dry_run:
                            task.delete()
                        cleaned_count += 1
                        
            except (ValueError, TypeError, IndexError) as e:
                # Invalid args format, clean up corrupted task
                self.stdout.write(f"  Corrupted task: {task.id} (error: {e})")
                if not dry_run:
                    task.delete()
                cleaned_count += 1
        
        return cleaned_count
