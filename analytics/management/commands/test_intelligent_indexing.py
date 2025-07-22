"""
Command to test intelligent indexing tasks with corrected arguments
"""
from django.core.management.base import BaseCommand
from django_q.tasks import async_task
from django_q.models import Task
from repositories.models import Repository


class Command(BaseCommand):
    help = 'Test intelligent indexing tasks with corrected arguments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Test with a specific repository ID',
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        
        if repository_id:
            try:
                repo = Repository.objects.get(id=repository_id)
            except Repository.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Repository {repository_id} not found"))
                return
            test_repos = [repo]
        else:
            # Use first indexed repository for testing
            test_repos = Repository.objects.filter(is_indexed=True)[:1]
            
        if not test_repos:
            self.stdout.write(self.style.ERROR("No indexed repositories found"))
            return
            
        repo = test_repos[0]
        user_id = repo.owner.id
        
        self.stdout.write(f"Testing with repository: {repo.full_name} (ID: {repo.id}, owner: {user_id})")
        
        # Test each intelligent indexing task
        test_functions = [
            ('analytics.tasks.index_commits_intelligent_task', [repo.id, user_id, 7]),
            ('analytics.tasks.index_deployments_intelligent_task', [repo.id, user_id, 30]),
            ('analytics.tasks.index_pullrequests_intelligent_task', [repo.id, user_id, 30]),
            ('analytics.tasks.index_releases_intelligent_task', [repo.id, user_id, 90]),
        ]
        
        created_tasks = []
        
        for func_name, test_args in test_functions:
            self.stdout.write(f"\n=== Testing {func_name} ===")
            
            try:
                # Create task with corrected args format
                task_id = async_task(func_name, *test_args)
                self.stdout.write(f"✅ Successfully created task: {task_id}")
                
                # Verify the task was created with correct arguments
                task = Task.objects.get(id=task_id)
                self.stdout.write(f"   - Task args: {task.args}")
                self.stdout.write(f"   - Task kwargs: {task.kwargs}")
                
                # Verify args format is correct
                if task.args == tuple(test_args):
                    self.stdout.write(self.style.SUCCESS("   ✅ Arguments format is CORRECT"))
                else:
                    self.stdout.write(self.style.ERROR(f"   ❌ Arguments format is WRONG: expected {tuple(test_args)}, got {task.args}"))
                
                created_tasks.append(task_id)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to create task: {e}"))
        
        # Summary
        self.stdout.write(f"\n=== SUMMARY ===")
        self.stdout.write(f"Created {len(created_tasks)} test tasks")
        for task_id in created_tasks:
            self.stdout.write(f"  - {task_id}")
        
        if created_tasks:
            self.stdout.write(f"\nTo monitor these tasks, run:")
            self.stdout.write(f"python manage.py qmonitor")
            
            self.stdout.write(f"\nTo clean up test tasks, run:")
            for task_id in created_tasks:
                self.stdout.write(f"python manage.py shell -c \"from django_q.models import Task; Task.objects.get(id='{task_id}').delete()\"")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Intelligent indexing argument format test completed!")) 