"""
Management command for calculating KLOC (Kilo Lines of Code) for repositories
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime

from repositories.models import Repository
from analytics.kloc_service import KLOCService
from analytics.git_service import GitService
from analytics.github_token_service import GitHubTokenService
from analytics.models import RepositoryKLOCHistory
from analytics.sanitization import assert_safe_repo_path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Calculate KLOC (Kilo Lines of Code) for repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-id',
            type=int,
            help='ID of a specific repository to calculate KLOC for'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Calculate KLOC for all repositories'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation even if KLOC was recently calculated'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be calculated without making changes'
        )

    def handle(self, *args, **options):
        if options['all']:
            self._calculate_all_repositories(options)
        elif options['repo_id']:
            self._calculate_single_repository(options['repo_id'], options)
        else:
            raise CommandError('Please specify either --repo-id or --all')

    def _calculate_single_repository(self, repo_id, options):
        """Calculate KLOC for a single repository"""
        try:
            repository = Repository.objects.get(id=repo_id)
        except Repository.DoesNotExist:
            raise CommandError(f'Repository with ID {repo_id} does not exist')

        self.stdout.write(f'Calculating KLOC for {repository.full_name}...')
        
        if options['dry_run']:
            self.stdout.write(f'[DRY RUN] Would calculate KLOC for {repository.full_name}')
            return

        # Check if KLOC was recently calculated (unless --force)
        if not options['force']:
            should_calculate, reason = repository.should_calculate_kloc(max_days=7)
            if not should_calculate:
                self.stdout.write(
                    self.style.WARNING(f'KLOC is recent: {reason}. Use --force to recalculate.')
                )
                return

        try:
            # Get GitHub token for cloning
            token = GitHubTokenService.get_token_for_repository_access(
                user_id=repository.owner.id,
                repo_full_name=repository.full_name
            )
            
            if not token:
                raise CommandError(f'No GitHub token available for repository {repository.full_name}')

            # Clone repository
            git_service = GitService()
            repo_path = git_service.clone_repository(
                repository.clone_url, 
                repository.full_name, 
                token
            )
            
            # Validate safe repo path
            try:
                safe_repo_path = str(assert_safe_repo_path(repo_path))
            except Exception as safe_err:
                raise CommandError(f'Unsafe repository path: {repo_path} - {safe_err}')

            # Calculate KLOC
            kloc_data = KLOCService.calculate_kloc(safe_repo_path)

            if options['dry_run']:
                self.stdout.write(f'[DRY RUN] KLOC result: {kloc_data}')
                return

            # Save KLOC history
            kloc_history = RepositoryKLOCHistory(
                repository_full_name=repository.full_name,
                repository_id=repository.id,
                kloc=kloc_data.get('kloc', 0.0),
                total_lines=kloc_data.get('total_lines', 0),
                language_breakdown=kloc_data.get('language_breakdown', {}),
                calculated_at=kloc_data.get('calculated_at'),
                total_files=len(kloc_data.get('language_breakdown', {})),
                code_files=sum(1 for ext_lines in kloc_data.get('language_breakdown', {}).values() if ext_lines > 0)
            )
            kloc_history.save()

            # Clean up cloned repository
            git_service.cleanup_repository(repository.full_name)

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ {repository.full_name}: {kloc_data.get("kloc", 0.0):.2f} KLOC '
                    f'({kloc_data.get("total_lines", 0)} lines, '
                    f'{len(kloc_data.get("language_breakdown", {}))} languages)'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ {repository.full_name}: {e}')
            )
            raise CommandError(f'Failed to calculate KLOC for {repository.full_name}: {e}')

    def _calculate_all_repositories(self, options):
        """Calculate KLOC for all repositories"""
        repositories = Repository.objects.all()
        
        if not repositories.exists():
            self.stdout.write(self.style.WARNING('No repositories found'))
            return

        self.stdout.write(f'Found {repositories.count()} repositories')

        success_count = 0
        error_count = 0
        
        for repo in repositories:
            try:
                self._calculate_single_repository(repo.id, options)
                success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ {repo.full_name}: {e}')
                )
                error_count += 1

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f'Completed: {success_count} successful, {error_count} errors')
        )
