"""
Management command to start intelligent indexing for repositories
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from repositories.models import Repository
from django_q.tasks import async_task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start intelligent indexing for repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Repository ID to index (default: all indexed repositories)',
        )
        parser.add_argument(
            '--entity-types',
            nargs='+',
            choices=['commits', 'pullrequests', 'releases', 'deployments'],
            default=['commits', 'pullrequests', 'releases', 'deployments'],
            help='Entity types to index (default: all)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be indexed without actually starting tasks',
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        entity_types = options['entity_types']
        dry_run = options['dry_run']
        
        # Get indexing service configuration
        indexing_service = getattr(settings, 'INDEXING_SERVICE', 'github_api')
        
        self.stdout.write(f"Indexing service: {indexing_service}")
        self.stdout.write(f"Entity types: {', '.join(entity_types)}")
        
        if repository_id:
            repositories = Repository.objects.filter(id=repository_id)
        else:
            repositories = Repository.objects.filter(is_indexed=True)
        
        self.stdout.write(f"Found {repositories.count()} repositories to index")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No tasks will be created"))
        
        for repo in repositories:
            self.stdout.write(f"\nRepository: {repo.full_name} (ID: {repo.id})")
            
            # Start indexing for each entity type
            for entity_type in entity_types:
                if entity_type == 'commits':
                    self.start_commit_indexing(repo, dry_run, indexing_service)
                elif entity_type == 'pullrequests':
                    self.start_pullrequest_indexing(repo, dry_run)
                elif entity_type == 'releases':
                    self.start_release_indexing(repo, dry_run)
                elif entity_type == 'deployments':
                    self.start_deployment_indexing(repo, dry_run)

    def start_commit_indexing(self, repo, dry_run, indexing_service):
        """Start commit indexing (respects INDEXING_SERVICE setting)"""
        if indexing_service == 'git_local':
            self.stdout.write(f"  Commits: Using Git local indexing (no rate limits)")
        else:
            self.stdout.write(f"  Commits: Using GitHub API indexing")
        
        if not dry_run:
            task_id = async_task(
                'analytics.tasks.index_commits_intelligent_task',
                repository_id=repo.id
            )
            self.stdout.write(f"    Task created: {task_id}")

    def start_pullrequest_indexing(self, repo, dry_run):
        """Start pull request indexing (always uses GitHub API)"""
        self.stdout.write(f"  Pull Requests: Using GitHub API (only option)")
        
        if not dry_run:
            task_id = async_task(
                'analytics.tasks.index_pullrequests_intelligent_task',
                repository_id=repo.id
            )
            self.stdout.write(f"    Task created: {task_id}")

    def start_release_indexing(self, repo, dry_run):
        """Start release indexing (always uses GitHub API)"""
        self.stdout.write(f"  Releases: Using GitHub API (only option)")
        
        if not dry_run:
            task_id = async_task(
                'analytics.tasks.index_releases_intelligent_task',
                repository_id=repo.id
            )
            self.stdout.write(f"    Task created: {task_id}")

    def start_deployment_indexing(self, repo, dry_run):
        """Start deployment indexing (always uses GitHub API)"""
        self.stdout.write(f"  Deployments: Using GitHub API (only option)")
        
        if not dry_run:
            task_id = async_task(
                'analytics.tasks.index_deployments_intelligent_task',
                repository_id=repo.id
            )
            self.stdout.write(f"    Task created: {task_id}")