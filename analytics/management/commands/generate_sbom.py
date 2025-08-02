"""
Management command for generating SBOMs
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django_q.tasks import async_task

from repositories.models import Repository
from analytics.models import SBOM

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate SBOM for repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-id',
            type=int,
            help='ID of a specific repository to generate SBOM for'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate SBOM for all indexed repositories'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force generation even if SBOM exists'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously instead of using Django-Q tasks'
        )

    def handle(self, *args, **options):
        if options['all']:
            self._generate_all_sboms(options)
        elif options['repo_id']:
            self._generate_single_sbom(options['repo_id'], options)
        else:
            raise CommandError('Please specify either --repo-id or --all')

    def _generate_single_sbom(self, repo_id, options):
        """Generate SBOM for a single repository"""
        try:
            if options['sync']:
                from analytics.tasks import generate_sbom_task
                result = generate_sbom_task(repo_id, options['force'])
            else:
                async_task('analytics.tasks.generate_sbom_task', repo_id, options['force'])
                result = {'status': 'scheduled'}
            
            self.stdout.write(
                self.style.SUCCESS(f"SBOM generation {'scheduled' if not options['sync'] else 'completed'} for repository {repo_id}"))
            
        except Exception as e:
            raise CommandError(f"Failed to generate SBOM for repository {repo_id}: {e}")

    def _generate_all_sboms(self, options):
        """Generate SBOM for all repositories"""
        repositories = Repository.objects.filter(is_indexed=True)
        
        for repo in repositories:
            try:
                if options['sync']:
                    from analytics.tasks import generate_sbom_task
                    result = generate_sbom_task(repo.id, options['force'])
                else:
                    async_task('analytics.tasks.generate_sbom_task', repo.id, options['force'])
                
                self.stdout.write(
                    self.style.SUCCESS(f"SBOM generation scheduled for {repo.full_name}"))
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to schedule SBOM generation for {repo.full_name}: {e}")) 