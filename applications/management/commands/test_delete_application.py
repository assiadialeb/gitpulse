"""
Management command to test application deletion with MongoDB cleanup
"""
from django.core.management.base import BaseCommand
from applications.models import Application
from analytics.models import Commit, SyncLog, RepositoryStats


class Command(BaseCommand):
    help = 'Test application deletion with MongoDB cleanup'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to delete')

    def handle(self, *args, **options):
        application_id = options['application_id']
        
        self.stdout.write(f"Testing application deletion for application {application_id}")
        
        try:
            # Check if application exists
            application = Application.objects.get(id=application_id)
            self.stdout.write(f"Found application: {application.name}")
            
            # Check MongoDB data before deletion
            commits_before = Commit.objects(application_id=application_id).count()
            sync_logs_before = SyncLog.objects(application_id=application_id).count()
            repo_stats_before = RepositoryStats.objects(application_id=application_id).count()
            
            self.stdout.write("MongoDB data before deletion:")
            self.stdout.write(f"  - Commits: {commits_before}")
            self.stdout.write(f"  - Sync logs: {sync_logs_before}")
            self.stdout.write(f"  - Repository stats: {repo_stats_before}")
            
            # Delete the application (this should trigger cleanup)
            application_name = application.name
            application.delete()
            
            # Check MongoDB data after deletion
            commits_after = Commit.objects(application_id=application_id).count()
            sync_logs_after = SyncLog.objects(application_id=application_id).count()
            repo_stats_after = RepositoryStats.objects(application_id=application_id).count()
            
            self.stdout.write("MongoDB data after deletion:")
            self.stdout.write(f"  - Commits: {commits_after}")
            self.stdout.write(f"  - Sync logs: {sync_logs_after}")
            self.stdout.write(f"  - Repository stats: {repo_stats_after}")
            
            # Verify cleanup
            if commits_after == 0 and sync_logs_after == 0 and repo_stats_after == 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Application "{application_name}" deleted successfully with all MongoDB data cleaned up!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Application deleted but some MongoDB data remains: {commits_after} commits, {sync_logs_after} sync logs, {repo_stats_after} repo stats')
                )
                
        except Application.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Application with ID {application_id} does not exist')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during deletion: {e}')
            )
            raise 