"""
Command to clean up all intelligent indexing tasks with corrupted arguments
"""
from django.core.management.base import BaseCommand
from django_q.models import Task, Schedule


class Command(BaseCommand):
    help = 'Clean up all intelligent indexing tasks with corrupted arguments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # List of intelligent indexing task functions to clean up
        task_functions = [
            'analytics.tasks.index_commits_intelligent_task',
            'analytics.tasks.index_deployments_intelligent_task', 
            'analytics.tasks.index_pullrequests_intelligent_task',
            'analytics.tasks.index_releases_intelligent_task'
        ]
        
        total_tasks_deleted = 0
        total_schedules_deleted = 0
        
        for func_name in task_functions:
            self.stdout.write(f"\n=== Cleaning up {func_name} ===")
            
            # Clean up pending/running tasks
            tasks = Task.objects.filter(func=func_name)
            task_count = tasks.count()
            
            if task_count > 0:
                if dry_run:
                    self.stdout.write(f"[DRY RUN] Would delete {task_count} tasks")
                    for task in tasks[:5]:  # Show first 5 as examples
                        self.stdout.write(f"  - Task {task.id}: args={task.args}, kwargs={task.kwargs}")
                else:
                    tasks.delete()
                    self.stdout.write(f"Deleted {task_count} tasks")
                total_tasks_deleted += task_count
            else:
                self.stdout.write("No tasks found")
            
            # Clean up scheduled tasks
            schedules = Schedule.objects.filter(func=func_name)
            schedule_count = schedules.count()
            
            if schedule_count > 0:
                if dry_run:
                    self.stdout.write(f"[DRY RUN] Would delete {schedule_count} schedules")
                    for schedule in schedules[:5]:  # Show first 5 as examples
                        self.stdout.write(f"  - Schedule {schedule.id}: args={schedule.args}, name={schedule.name}")
                else:
                    schedules.delete()
                    self.stdout.write(f"Deleted {schedule_count} schedules")
                total_schedules_deleted += schedule_count
            else:
                self.stdout.write("No schedules found")
        
        # Summary
        self.stdout.write(f"\n=== SUMMARY ===")
        if dry_run:
            self.stdout.write(f"[DRY RUN] Would delete:")
            self.stdout.write(f"  - {total_tasks_deleted} tasks")
            self.stdout.write(f"  - {total_schedules_deleted} schedules")
        else:
            self.stdout.write(f"Successfully deleted:")
            self.stdout.write(f"  - {total_tasks_deleted} tasks")
            self.stdout.write(f"  - {total_schedules_deleted} schedules")
        
        self.stdout.write("\nAll intelligent indexing tasks have been cleaned up!") 