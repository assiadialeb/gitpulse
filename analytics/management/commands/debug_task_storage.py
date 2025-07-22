"""
Command to inspect Django-Q task storage directly
"""
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from django_q.models import Task
from repositories.models import Repository
import json


class Command(BaseCommand):
    help = 'Inspect how Django-Q stores task arguments in database'

    def handle(self, *args, **options):
        # Get first repository
        repo = Repository.objects.filter(is_indexed=True).first()
        if not repo:
            self.stdout.write(self.style.ERROR("No indexed repositories found"))
            return
            
        self.stdout.write(f"Testing with repository: {repo.full_name} (ID: {repo.id})")
        
        # Clean up any existing test tasks first
        Task.objects.filter(func='analytics.tasks.index_commits_intelligent_task').delete()
        
        # Test different ways of calling async_task
        test_cases = [
            ("Positional args", 'analytics.tasks.index_commits_intelligent_task', repo.id, 7),
            ("List as single arg", 'analytics.tasks.index_commits_intelligent_task', [repo.id, 7]),
            ("Args parameter", 'analytics.tasks.index_commits_intelligent_task', 'args', [repo.id, 7]),
        ]
        
        for test_name, func_name, *func_args in test_cases:
            self.stdout.write(f"\n=== Testing: {test_name} ===")
            
            try:
                # Create task
                if func_args and isinstance(func_args[0], list):
                    # List as single arg
                    task_id = async_task(func_name, func_args[0])
                elif len(func_args) > 1 and func_args[0] == 'args':
                    # Args parameter
                    task_id = async_task(func_name, args=func_args[1])
                else:
                    # Positional args
                    task_id = async_task(func_name, *func_args)
                
                self.stdout.write(f"✅ Created task: {task_id}")
                
                # Get task details from database
                try:
                    task = Task.objects.get(id=task_id)
                    self.stdout.write(f"   - Func: {task.func}")
                    self.stdout.write(f"   - Args: {task.args} (type: {type(task.args)})")
                    self.stdout.write(f"   - Kwargs: {task.kwargs} (type: {type(task.kwargs)})")
                    
                    # Detailed analysis
                    if isinstance(task.args, tuple):
                        self.stdout.write(f"   - Args is tuple with {len(task.args)} elements")
                        for i, arg in enumerate(task.args):
                            self.stdout.write(f"     [{i}]: {arg} (type: {type(arg)})")
                    else:
                        self.stdout.write(f"   - Args is not tuple: {type(task.args)}")
                        
                except Task.DoesNotExist:
                    self.stdout.write(self.style.WARNING("   ⚠️  Task not found in database"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed: {e}"))
        
        # Clean up
        self.stdout.write(f"\n=== CLEANUP ===")
        Task.objects.filter(func='analytics.tasks.index_commits_intelligent_task').delete()
        self.stdout.write("Cleaned up test tasks")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Debug completed!")) 