from django.core.management.base import BaseCommand
from repositories.models import Repository
from analytics.models import IndexingState
from django_q.models import Schedule
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reset indexing state for a repository'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            required=True,
            help='Repository ID to reset indexing state for',
        )
        parser.add_argument(
            '--entity-type',
            choices=['commits', 'pull_requests', 'releases', 'deployments', 'codeql_vulnerabilities', 'all'],
            default='all',
            help='Entity type to reset (default: all)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be reset without actually doing it',
        )

    def handle(self, *args, **options):
        repository_id = options['repository_id']
        entity_type = options['entity_type']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
        
        try:
            repository = Repository.objects.get(id=repository_id)
        except Repository.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Repository {repository_id} not found"))
            return
        
        self.stdout.write(f"Repository: {repository.full_name} (ID: {repository_id})")
        
        # Reset indexing states
        if entity_type == 'all':
            states = IndexingState.objects.filter(repository_id=repository_id)
        else:
            states = IndexingState.objects.filter(repository_id=repository_id, entity_type=entity_type)
        
        state_count = states.count()
        self.stdout.write(f"Found {state_count} indexing states to reset")
        
        if state_count == 0:
            self.stdout.write("No indexing states found")
            return
        
        for state in states:
            self.stdout.write(f"  {state.entity_type}: {state.status} -> pending")
            if not dry_run:
                state.status = 'pending'
                state.last_run_at = None
                state.retry_count = 0
                state.save()
        
        # Clean up scheduled tasks for this repository
        scheduled_tasks = Schedule.objects.filter(
            func__in=[
                'analytics.tasks.index_commits_intelligent_task',
                'analytics.tasks.index_pullrequests_intelligent_task',
                'analytics.tasks.index_releases_intelligent_task',
                'analytics.tasks.index_deployments_intelligent_task',
                'analytics.tasks.index_codeql_intelligent_task',
            ]
        )
        
        tasks_to_delete = []
        for task in scheduled_tasks:
            if task.args and len(task.args) > 0:
                task_repo_id = task.args[0]
                if isinstance(task_repo_id, list):
                    task_repo_id = task_repo_id[0]
                
                if task_repo_id == repository_id:
                    tasks_to_delete.append(task)
        
        if tasks_to_delete:
            self.stdout.write(f"Found {len(tasks_to_delete)} scheduled tasks to delete")
            for task in tasks_to_delete:
                self.stdout.write(f"  {task.name}: {task.func}")
                if not dry_run:
                    task.delete()
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Successfully reset indexing state for {repository.full_name}"))
        else:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes made"))
