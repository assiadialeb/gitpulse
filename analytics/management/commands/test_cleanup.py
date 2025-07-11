"""
Management command to test MongoDB cleanup functionality
"""
from django.core.management.base import BaseCommand
from applications.models import Application
from analytics.services import cleanup_application_data


class Command(BaseCommand):
    help = 'Test MongoDB cleanup for an application'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to test cleanup for')

    def handle(self, *args, **options):
        application_id = options['application_id']
        
        self.stdout.write(f"Testing MongoDB cleanup for application {application_id}")
        
        try:
            # Check if application exists
            application = Application.objects.get(id=application_id)
            self.stdout.write(f"Found application: {application.name}")
            
            # Test cleanup
            cleanup_results = cleanup_application_data(application_id)
            
            self.stdout.write("Cleanup results:")
            self.stdout.write(f"  - Commits deleted: {cleanup_results['commits_deleted']}")
            self.stdout.write(f"  - Sync logs deleted: {cleanup_results['sync_logs_deleted']}")
            self.stdout.write(f"  - Repository stats deleted: {cleanup_results['repository_stats_deleted']}")
            self.stdout.write(f"  - Total deleted: {cleanup_results['total_deleted']}")
            
            if 'error' in cleanup_results:
                self.stdout.write(
                    self.style.ERROR(f"Error during cleanup: {cleanup_results['error']}")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('✓ Cleanup completed successfully!')
                )
                
        except Application.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Application with ID {application_id} does not exist')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing cleanup: {e}')
            )
            raise 