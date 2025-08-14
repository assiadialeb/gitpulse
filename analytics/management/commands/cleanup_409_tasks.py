from django.core.management.base import BaseCommand
from django_q.models import Task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up tasks that failed due to 409 Conflict errors'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually deleting',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum number of retries before cleaning up (default: 3)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_retries = options['max_retries']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No tasks will be deleted"))
        
        self.stdout.write("Cleaning up tasks with 409 Conflict errors...")
        
        # Find tasks that failed due to 409 Conflict
        failed_tasks = Task.objects.filter(success=False)
        
        # Filter by retry count and 409 error
        tasks_to_clean = []
        for task in failed_tasks:
            if task.attempt_count >= max_retries:
                # Check if the result contains 409 error
                if task.result and isinstance(task.result, str) and '409 Client Error: Conflict' in task.result:
                    tasks_to_clean.append(task)
        
        count = len(tasks_to_clean)
        self.stdout.write(f"Found {count} tasks with 409 Conflict errors and {max_retries}+ retries")
        
        if count == 0:
            self.stdout.write("No tasks need cleanup")
            return
        
        cleaned_count = 0
        
        for task in tasks_to_clean:
            # Extract repository info from task args if possible
            repo_info = "unknown"
            try:
                if task.args and len(task.args) > 0:
                    repo_id = task.args[0]
                    if isinstance(repo_id, list):
                        repo_id = repo_id[0]
                    repo_info = f"repository_id: {repo_id}"
            except:
                pass
            
            self.stdout.write(f"  Task {task.id}: {task.func} ({repo_info}) - {task.attempt_count} attempts")
            
            if not dry_run:
                task.delete()
                cleaned_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"Cleanup completed: {cleaned_count} tasks {'would be ' if dry_run else ''}deleted")
        )
