"""
Command to verify task execution by creating one test task and monitoring it
"""
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from django_q.models import Task
from repositories.models import Repository
import time


class Command(BaseCommand):
    help = 'Create one test task and verify it executes without errors'

    def handle(self, *args, **options):
        # Use first repository for testing
        try:
            repo = Repository.objects.filter(is_indexed=True).first()
            if not repo:
                self.stdout.write(self.style.ERROR("No indexed repositories found"))
                return
                
            user_id = repo.owner.id
            
            self.stdout.write(f"Creating test task for repository: {repo.full_name} (ID: {repo.id}, owner: {user_id})")
            
            # Create one test task with corrected syntax
            task_id = async_task(
                'analytics.tasks.index_commits_intelligent_task',
                repo.id, 7
            )
            
            self.stdout.write(f"✅ Created test task: {task_id}")
            
            # Give some time for the task to be processed
            self.stdout.write("Waiting 5 seconds for task to be processed...")
            time.sleep(5)
            
            # Check if task still exists (if it exists, it might be failed)
            try:
                task = Task.objects.get(id=task_id)
                self.stdout.write(self.style.WARNING(f"⚠️  Task still exists in queue: {task.func}"))
                self.stdout.write(f"   Args: {task.args}")
                self.stdout.write(f"   Kwargs: {task.kwargs}")
                if hasattr(task, 'result'):
                    self.stdout.write(f"   Result: {task.result}")
            except Task.DoesNotExist:
                self.stdout.write(self.style.SUCCESS("✅ Task was processed and removed from queue (likely successful)"))
            
            self.stdout.write("\n📝 Check the Q worker logs above for any error messages!")
            self.stdout.write("   - If you see 'INFO Process-xxx processing ...' without errors, it worked!")
            self.stdout.write("   - If you see 'ERROR Failed ...' then there's still an issue.")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}")) 