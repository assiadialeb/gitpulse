"""
Management command for indexing GitHub commits with PR links
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_q.tasks import async_task

from repositories.models import Repository
from analytics.commit_indexing_service import CommitIndexingService
from analytics.github_token_service import GitHubTokenService
from analytics.models import IndexingState

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Index GitHub commits for repositories using intelligent indexing with PR links'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-id',
            type=int,
            help='ID of a specific repository to index commits for'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Index commits for all indexed repositories'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=7,
            help='Number of days per batch (default: 7)'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously instead of using Django-Q tasks'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset indexing state before starting'
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show indexing status for repositories'
        )

    def handle(self, *args, **options):
        if options['status']:
            self._show_status(options)
            return

        if options['reset']:
            self._reset_indexing_state(options)

        if options['all']:
            self._index_all_repositories(options)
        elif options['repo_id']:
            self._index_single_repository(options['repo_id'], options)
        else:
            raise CommandError('Please specify either --repo-id or --all')

    def _show_status(self, options):
        """Show indexing status for all repositories"""
        self.stdout.write(self.style.SUCCESS('Commit Indexing Status:'))
        self.stdout.write('-' * 80)
        
        repositories = Repository.objects.filter(is_indexed=True)
        
        for repo in repositories:
            try:
                state = IndexingState.objects.get(
                    repository_id=repo.id,
                    entity_type='commits'
                )
                
                self.stdout.write(f"Repository: {repo.full_name} (ID: {repo.id})")
                self.stdout.write(f"  Status: {state.status}")
                self.stdout.write(f"  Total Indexed: {state.total_indexed}")
                self.stdout.write(f"  Last Indexed At: {state.last_indexed_at}")
                self.stdout.write(f"  Last Run At: {state.last_run_at}")
                if state.error_message:
                    self.stdout.write(f"  Error: {state.error_message}")
                self.stdout.write("")
                
            except IndexingState.DoesNotExist:
                self.stdout.write(f"Repository: {repo.full_name} (ID: {repo.id})")
                self.stdout.write("  Status: Not started")
                self.stdout.write("")

    def _reset_indexing_state(self, options):
        """Reset indexing state"""
        if options['repo_id']:
            # Reset specific repository
            try:
                state = IndexingState.objects.get(
                    repository_id=options['repo_id'],
                    entity_type='commits'
                )
                state.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"Reset commit indexing state for repository {options['repo_id']}")
                )
            except IndexingState.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"No commit indexing state found for repository {options['repo_id']}")
                )
        else:
            # Reset all repositories
            count = IndexingState.objects.filter(entity_type='commits').delete()[0]
            self.stdout.write(
                self.style.SUCCESS(f"Reset commit indexing state for {count} repositories")
            )

    def _index_single_repository(self, repo_id, options):
        """Index commits for a single repository"""
        try:
            repository = Repository.objects.get(id=repo_id)
        except Repository.DoesNotExist:
            raise CommandError(f'Repository with ID {repo_id} does not exist')

        if not repository.is_indexed:
            raise CommandError(f'Repository {repository.full_name} is not indexed')

        self.stdout.write(f'Starting commit indexing for {repository.full_name}...')

        if options['sync']:
            # Run synchronously
            try:
                result = CommitIndexingService.index_commits_for_repository(
                    repository_id=repo_id,
                    user_id=repository.owner.id,
                    batch_size_days=options['batch_size']
                )

                self.stdout.write(
                    self.style.SUCCESS(f'Commit indexing completed: {result}')
                )

                # If there's more to index, ask if user wants to continue
                if result.get('has_more', False):
                    self.stdout.write(
                        self.style.WARNING(
                            'There are more commits to index. '
                            'Run the command again to continue or use --all with Django-Q tasks.'
                        )
                    )

            except Exception as e:
                raise CommandError(f'Commit indexing failed: {e}')
        else:
            # Run asynchronously with Django-Q
            try:
                task_id = async_task(
                    'analytics.tasks.index_commits_intelligent_task',
                    repo_id,
                    repository.owner.id,
                    options['batch_size']
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Commit indexing task scheduled with ID: {task_id}')
                )
            except Exception as e:
                raise CommandError(f'Failed to schedule commit indexing task: {e}')

    def _index_all_repositories(self, options):
        """Index commits for all repositories"""
        repositories = Repository.objects.filter(is_indexed=True)
        
        if not repositories.exists():
            self.stdout.write(self.style.WARNING('No indexed repositories found'))
            return

        self.stdout.write(f'Found {repositories.count()} indexed repositories')

        if options['sync']:
            # Run synchronously for all repositories
            success_count = 0
            error_count = 0
            
            for repo in repositories:
                try:
                    self.stdout.write(f'Processing {repo.full_name}...')
                    
                    result = CommitIndexingService.index_commits_for_repository(
                        repository_id=repo.id,
                        user_id=repo.owner.id,
                        batch_size_days=options['batch_size']
                    )

                    self.stdout.write(
                        self.style.SUCCESS(f'✓ {repo.full_name}: {result.get("processed", 0)} commits processed')
                    )
                    success_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'✗ {repo.full_name}: {e}')
                    )
                    error_count += 1

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'Completed: {success_count} successful, {error_count} errors'))
        else:
            # Run asynchronously with Django-Q
            try:
                task_id = async_task('analytics.tasks.index_all_commits_task')
                self.stdout.write(
                    self.style.SUCCESS(f'Commit indexing task for all repositories scheduled with ID: {task_id}')
                )
            except Exception as e:
                raise CommandError(f'Failed to schedule commit indexing task: {e}') 