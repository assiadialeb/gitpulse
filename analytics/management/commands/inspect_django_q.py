"""
Command to inspect Django-Q database directly
"""
from django.core.management.base import BaseCommand
from django_q.models import Task, Schedule
from repositories.models import Repository


class Command(BaseCommand):
    help = 'Inspect Django-Q database for task storage patterns'

    def handle(self, *args, **options):
        self.stdout.write("=== INSPECTING DJANGO-Q DATABASE ===")
        
        # Check existing tasks
        tasks = Task.objects.all()
        self.stdout.write(f"\nTotal tasks in database: {tasks.count()}")
        
        if tasks.exists():
            self.stdout.write("\n=== SAMPLE TASKS ===")
            for task in tasks[:5]:  # Show first 5 tasks
                self.stdout.write(f"\nTask ID: {task.id}")
                self.stdout.write(f"  Func: {task.func}")
                self.stdout.write(f"  Args: {task.args} (type: {type(task.args)})")
                self.stdout.write(f"  Kwargs: {task.kwargs} (type: {type(task.kwargs)})")
                
                if isinstance(task.args, tuple):
                    self.stdout.write(f"  Args is tuple with {len(task.args)} elements")
                    for i, arg in enumerate(task.args):
                        self.stdout.write(f"    [{i}]: {arg} (type: {type(arg)})")
        
        # Check schedules
        schedules = Schedule.objects.all()
        self.stdout.write(f"\nTotal schedules in database: {schedules.count()}")
        
        if schedules.exists():
            self.stdout.write("\n=== SAMPLE SCHEDULES ===")
            for schedule in schedules[:3]:  # Show first 3 schedules
                self.stdout.write(f"\nSchedule ID: {schedule.id}")
                self.stdout.write(f"  Func: {schedule.func}")
                self.stdout.write(f"  Args: {schedule.args} (type: {type(schedule.args)})")
                self.stdout.write(f"  Kwargs: {schedule.kwargs} (type: {type(schedule.kwargs)})")
        
        # Check for intelligent indexing tasks specifically
        intelligent_tasks = Task.objects.filter(
            func__in=[
                'analytics.tasks.index_commits_intelligent_task',
                'analytics.tasks.index_deployments_intelligent_task',
                'analytics.tasks.index_pullrequests_intelligent_task',
                'analytics.tasks.index_releases_intelligent_task'
            ]
        )
        
        self.stdout.write(f"\n=== INTELLIGENT INDEXING TASKS ===")
        self.stdout.write(f"Found {intelligent_tasks.count()} intelligent indexing tasks")
        
        for task in intelligent_tasks:
            self.stdout.write(f"\nTask ID: {task.id}")
            self.stdout.write(f"  Func: {task.func}")
            self.stdout.write(f"  Args: {task.args} (type: {type(task.args)})")
            self.stdout.write(f"  Kwargs: {task.kwargs} (type: {type(task.kwargs)})")
            
            if isinstance(task.args, tuple):
                self.stdout.write(f"  Args is tuple with {len(task.args)} elements")
                for i, arg in enumerate(task.args):
                    self.stdout.write(f"    [{i}]: {arg} (type: {type(arg)})")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Inspection completed!")) 