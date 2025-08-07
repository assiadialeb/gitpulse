from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from repositories.models import Repository
from analytics.security_health_score_service import SecurityHealthScoreService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Calculate Security Health Score (SHS) for all repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Calculate SHS for a specific repository ID'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recalculation even if SHS already exists'
        )

    def handle(self, *args, **options):
        repository_id = options.get('repository_id')
        force = options.get('force')
        
        shs_service = SecurityHealthScoreService()
        
        if repository_id:
            # Calculate for specific repository
            try:
                repository = Repository.objects.get(id=repository_id)
                self._calculate_shs_for_repository(repository, shs_service, force)
            except Repository.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Repository with ID {repository_id} not found')
                )
        else:
            # Calculate for all repositories
            repositories = Repository.objects.filter(is_indexed=True)
            self.stdout.write(f'Calculating SHS for {repositories.count()} repositories...')
            
            for repository in repositories:
                self._calculate_shs_for_repository(repository, shs_service, force)
            
            self.stdout.write(
                self.style.SUCCESS('SHS calculation completed for all repositories')
            )
    
    def _calculate_shs_for_repository(self, repository, shs_service, force):
        """Calculate SHS for a specific repository"""
        try:
            # Check if SHS already exists and we're not forcing
            if not force:
                from analytics.models import SecurityHealthHistory
                existing = SecurityHealthHistory.objects.filter(
                    repository_full_name=repository.full_name
                ).first()
                
                if existing:
                    self.stdout.write(
                        f'SHS already exists for {repository.full_name}: {existing.shs_score:.1f}/100'
                    )
                    return
            
            # Calculate SHS
            kloc = repository.kloc or 0.0
            result = shs_service.calculate_shs(repository.full_name, repository.id, kloc)
            
            if result['shs_score'] is not None:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'{repository.full_name}: SHS {result["shs_score"]:.1f}/100 '
                        f'({result["total_vulnerabilities"]} vulnerabilities)'
                    )
                )
            else:
                self.stdout.write(
                    f'{repository.full_name}: {result["status"]} - {result["message"]}'
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error calculating SHS for {repository.full_name}: {e}')
            ) 