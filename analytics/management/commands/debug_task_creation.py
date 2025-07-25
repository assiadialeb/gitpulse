"""
Command to debug how Django-Q stores task arguments
"""
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from django_q.models import Task
from repositories.models import Repository
import time


class Command(BaseCommand):
    help = 'Debug how Django-Q stores task arguments'

    def handle(self, *args, **options):
        # Get first repository
        repo = Repository.objects.filter(is_indexed=True).first()
        if not repo:
            self.stdout.write(self.style.ERROR("No indexed repositories found"))
            return
            
        self.stdout.write(f"Testing with repository: {repo.full_name} (ID: {repo.id})")
        
        # Test different ways of calling async_task
        test_cases = [
            ("Positional args", 'analytics.tasks.index_commits_intelligent_task', repo.id, 7),
            ("List as single arg", 'analytics.tasks.index_commits_intelligent_task', [repo.id, 7]),
            ("Args parameter", 'analytics.tasks.index_commits_intelligent_task', 'args', [repo.id, 7]),
        ]
        
        created_tasks = []
        
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
                
                # Get task details immediately before it's processed
                import time
                time.sleep(0.1)  # Small delay to ensure task is saved
                
                try:
                    task = Task.objects.get(id=task_id)
                    self.stdout.write(f"   - Func: {task.func}")
                    self.stdout.write(f"   - Args: {task.args} (type: {type(task.args)})")
                    self.stdout.write(f"   - Kwargs: {task.kwargs} (type: {type(task.kwargs)})")
                    
                    # Check if args is a list containing a list
                    if isinstance(task.args, tuple) and len(task.args) == 1 and isinstance(task.args[0], list):
                        self.stdout.write(self.style.WARNING("   ⚠️  Args is tuple containing list: [(repo_id, batch_size)]"))
                    elif isinstance(task.args, tuple) and len(task.args) == 2:
                        self.stdout.write(self.style.SUCCESS("   ✅ Args is tuple with 2 elements: (repo_id, batch_size)"))
                    else:
                        self.stdout.write(self.style.ERROR(f"   ❌ Unexpected args format: {task.args}"))
                        
                except Task.DoesNotExist:
                    self.stdout.write(self.style.WARNING("   ⚠️  Task was already processed and removed"))
                
                created_tasks.append(task_id)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed: {e}"))
        
        # Clean up test tasks
        self.stdout.write(f"\n=== CLEANUP ===")
        for task_id in created_tasks:
            try:
                Task.objects.get(id=task_id).delete()
                self.stdout.write(f"Deleted task: {task_id}")
            except:
                pass
        
        self.stdout.write(self.style.SUCCESS("\n✅ Debug completed!")) 