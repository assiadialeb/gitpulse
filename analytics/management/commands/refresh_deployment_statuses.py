from django.core.management.base import BaseCommand, CommandError
from analytics.models import Deployment
from analytics.deployment_indexing_service import DeploymentIndexingService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh deployment statuses for existing deployments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo-id',
            type=int,
            help='Repository ID to refresh statuses for'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Refresh statuses for all repositories'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Limit number of deployments to process (default: 100)'
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            self.stdout.write('')

        if options['repo_id']:
            self._refresh_repository_deployments(options['repo_id'], options)
        elif options['all']:
            self._refresh_all_deployments(options)
        else:
            raise CommandError('Please specify either --repo-id or --all')

    def _refresh_repository_deployments(self, repo_id, options):
        """Refresh statuses for a specific repository"""
        from repositories.models import Repository
        
        try:
            repository = Repository.objects.get(id=repo_id)
        except Repository.DoesNotExist:
            raise CommandError(f'Repository with ID {repo_id} not found')

        self.stdout.write(f'Refreshing deployment statuses for repository: {repository.full_name}')
        self._process_deployments(repository.full_name, options)

    def _refresh_all_deployments(self, options):
        """Refresh statuses for all repositories"""
        # Get unique repository names from deployments
        repository_names = Deployment.objects.distinct('repository_full_name')
        
        self.stdout.write(f'Found {len(repository_names)} repositories with deployments')
        
        for repo_name in repository_names:
            if repo_name:  # Skip empty repository names
                self.stdout.write(f'Processing repository: {repo_name}')
                self._process_deployments(repo_name, options)

    def _process_deployments(self, repository_full_name, options):
        """Process deployments for a specific repository"""
        if not repository_full_name or '/' not in repository_full_name:
            self.stdout.write(self.style.WARNING(f'Skipping invalid repository name: {repository_full_name}'))
            return

        owner, repo = repository_full_name.split('/', 1)
        
        # Get deployments that need status refresh (empty statuses or limited count)
        deployments = Deployment.objects.filter(
            repository_full_name=repository_full_name
        ).order_by('-created_at')[:options['limit']]

        self.stdout.write(f'Found {deployments.count()} deployments to process')

        processed = 0
        updated = 0
        errors = 0

        for deployment in deployments:
            try:
                processed += 1
                
                # Check if statuses need refresh
                needs_refresh = not deployment.statuses or len(deployment.statuses) == 0
                
                if not needs_refresh:
                    continue

                if options['dry_run']:
                    self.stdout.write(f'  Would refresh statuses for deployment {deployment.deployment_id}')
                    continue

                # Fetch statuses from GitHub
                statuses = DeploymentIndexingService.fetch_deployment_statuses(
                    owner, repo, deployment.deployment_id, None
                )

                if statuses:
                    deployment.statuses = statuses
                    deployment.save()
                    updated += 1
                    
                    # Show status states
                    states = [s.get('state', 'unknown') for s in statuses]
                    self.stdout.write(f'  Updated deployment {deployment.deployment_id}: {len(statuses)} statuses - {states}')
                else:
                    self.stdout.write(f'  No statuses found for deployment {deployment.deployment_id}')

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f'  Error processing deployment {deployment.deployment_id}: {e}'))

        self.stdout.write('')
        self.stdout.write(f'Repository {repository_full_name}:')
        self.stdout.write(f'  Processed: {processed}')
        if not options['dry_run']:
            self.stdout.write(f'  Updated: {updated}')
        self.stdout.write(f'  Errors: {errors}')
        self.stdout.write('')

    def _show_summary(self, options):
        """Show summary of deployment statuses"""
        total_deployments = Deployment.objects.count()
        deployments_with_statuses = Deployment.objects.filter(statuses__exists=True, statuses__ne=[]).count()
        deployments_without_statuses = total_deployments - deployments_with_statuses

        self.stdout.write(self.style.SUCCESS('Deployment Status Summary:'))
        self.stdout.write('-' * 50)
        self.stdout.write(f'Total deployments: {total_deployments}')
        self.stdout.write(f'With statuses: {deployments_with_statuses}')
        self.stdout.write(f'Without statuses: {deployments_without_statuses}')
        self.stdout.write('')
