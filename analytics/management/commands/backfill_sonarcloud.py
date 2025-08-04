from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from repositories.models import Repository
from analytics.sonarcloud_service import SonarCloudService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill historical SonarCloud data for repositories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Specific repository ID to backfill'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Number of days to backfill (default: 90)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Backfill all repositories'
        )
        parser.add_argument(
            '--from-date',
            type=str,
            help='Start date for backfill (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--to-date',
            type=str,
            help='End date for backfill (YYYY-MM-DD)'
        )

    def handle(self, *args, **options):
        sonar_service = SonarCloudService()
        
        # Determine date range
        if options['from_date'] and options['to_date']:
            from_date = datetime.strptime(options['from_date'], '%Y-%m-%d')
            to_date = datetime.strptime(options['to_date'], '%Y-%m-%d')
        else:
            to_date = timezone.now()
            from_date = to_date - timedelta(days=options['days'])
        
        self.stdout.write(f"Backfilling SonarCloud data from {from_date.date()} to {to_date.date()}")
        
        # Get repositories to process
        if options['repository_id']:
            repositories = Repository.objects.filter(id=options['repository_id'])
        elif options['all']:
            repositories = Repository.objects.all()
        else:
            self.stdout.write(self.style.ERROR('Please specify --repository-id or --all'))
            return
        
        total_repositories = repositories.count()
        self.stdout.write(f"Processing {total_repositories} repositories...")
        
        success_count = 0
        error_count = 0
        
        for i, repository in enumerate(repositories, 1):
            self.stdout.write(f"[{i}/{total_repositories}] Processing {repository.full_name}...")
            
            try:
                result = sonar_service.backfill_historical_data(
                    repository_id=repository.id,
                    repository_full_name=repository.full_name,
                    from_date=from_date,
                    to_date=to_date
                )
                
                if result['success']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ {repository.full_name}: {result['data_points_stored']} data points stored "
                            f"({result['analyses_found']} analyses found)"
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ {repository.full_name}: {result.get('error', 'Unknown error')}"
                        )
                    )
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ {repository.full_name}: {str(e)}")
                )
                error_count += 1
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("BACKFILL SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Total repositories: {total_repositories}")
        self.stdout.write(f"Successful: {success_count}")
        self.stdout.write(f"Failed: {error_count}")
        self.stdout.write(f"Date range: {from_date.date()} to {to_date.date()}")
        
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Backfill completed successfully for {success_count} repositories!")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"\n✗ Backfill failed for all repositories!")
            ) 