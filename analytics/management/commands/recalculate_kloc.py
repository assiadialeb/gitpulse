from django.core.management.base import BaseCommand
from repositories.models import Repository
from analytics.kloc_service import KLOCService
from analytics.git_service import GitService
from analytics.github_token_service import GitHubTokenService
from analytics.sanitization import assert_safe_repo_path
from analytics.models import RepositoryKLOCHistory
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recalculate KLOC for repositories with 0.0 KLOC but non-zero size'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Specific repository ID to recalculate KLOC for',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be recalculated without actually doing it',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation even if KLOC was calculated recently',
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No KLOC will be recalculated"))
        
        if repository_id:
            repositories = Repository.objects.filter(id=repository_id)
        else:
            # Find repositories with 0.0 KLOC but non-zero size
            repositories = Repository.objects.filter(
                kloc=0.0,
                size__gt=0  # Repository has some content
            )
            
            if not force:
                # Only include repositories where KLOC was never calculated or calculated more than 7 days ago
                from django.utils import timezone
                from datetime import timedelta
                cutoff_date = timezone.now() - timedelta(days=7)
                from django.db.models import Q
                repositories = repositories.filter(
                    Q(kloc_calculated_at__isnull=True) | 
                    Q(kloc_calculated_at__lt=cutoff_date)
                )
        
        count = repositories.count()
        self.stdout.write(f"Found {count} repositories to recalculate KLOC for")
        
        if count == 0:
            self.stdout.write("No repositories need KLOC recalculation")
            return
        
        success_count = 0
        error_count = 0
        
        for repo in repositories:
            self.stdout.write(f"\nProcessing {repo.full_name} (ID: {repo.id})...")
            
            if dry_run:
                self.stdout.write(f"  Would recalculate KLOC for {repo.full_name}")
                continue
            
            try:
                result = self.recalculate_kloc_for_repository(repo)
                if result['success']:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ KLOC recalculated: {result['kloc']:.2f} KLOC, "
                            f"{result['total_lines']} lines, {result['total_files']} files"
                        )
                    )
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Failed: {result['error']}")
                    )
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Exception: {e}")
                )
        
        self.stdout.write(f"\nRecalculation completed:")
        self.stdout.write(f"  Success: {success_count}")
        self.stdout.write(f"  Errors: {error_count}")

    def recalculate_kloc_for_repository(self, repository: Repository) -> dict:
        """Recalculate KLOC for a specific repository"""
        try:
            # Get a token for cloning
            token = GitHubTokenService.get_token_for_repository_access(
                repository.owner.id, 
                repository.full_name
            )
            
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
                return {
                    'success': False,
                    'error': f"Unsafe repository path: {safe_err}"
                }
            
            # Calculate KLOC
            kloc_service = KLOCService()
            kloc_data = kloc_service.calculate_kloc(safe_repo_path)
            
            # Update repository
            repository.kloc = kloc_data.get('kloc', 0.0)
            repository.kloc_calculated_at = timezone.now()
            repository.save()
            
            # Save KLOC history
            try:
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
            except Exception as mongo_err:
                logger.warning(f"Failed to save KLOC history for {repository.full_name}: {mongo_err}")
            
            # Cleanup
            try:
                import tempfile
                import os
                import shutil
                repo_path_unsanitized = os.path.join(tempfile.gettempdir(), f"gitpulse_{repository.full_name.replace('/', '_')}")
                if os.path.exists(repo_path_unsanitized):
                    shutil.rmtree(repo_path_unsanitized)
                    logger.info(f"Cleaned up cloned repository for {repository.full_name}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup repository for {repository.full_name}: {cleanup_err}")
            
            return {
                'success': True,
                'kloc': kloc_data.get('kloc', 0.0),
                'total_lines': kloc_data.get('total_lines', 0),
                'total_files': len(kloc_data.get('language_breakdown', {})),
                'languages': kloc_data.get('language_breakdown', {})
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
