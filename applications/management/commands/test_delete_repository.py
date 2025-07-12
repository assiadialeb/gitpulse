"""
Management command to test repository deletion with MongoDB cleanup
"""
from django.core.management.base import BaseCommand
from applications.models import Application, ApplicationRepository
from analytics.models import Commit, SyncLog, RepositoryStats


class Command(BaseCommand):
    help = 'Test repository deletion with MongoDB cleanup'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID')
        parser.add_argument('repository_name', type=str, help='Repository name (owner/repo)')

    def handle(self, *args, **options):
        application_id = options['application_id']
        repository_name = options['repository_name']
        
        self.stdout.write(f"Testing repository deletion for {repository_name} in application {application_id}")
        
        try:
            # Check if application exists
            application = Application.objects.get(id=application_id)
            self.stdout.write(f"Found application: {application.name}")
            
            # Check if repository exists
            try:
                repository = ApplicationRepository.objects.get(
                    application=application,
                    github_repo_name=repository_name
                )
                self.stdout.write(f"Found repository: {repository.github_repo_name}")
            except ApplicationRepository.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Repository {repository_name} not found in application {application_id}')
                )
                return
            
            # Check MongoDB data before deletion
            commits_before = Commit.objects(repository_full_name=repository_name).count()
            sync_logs_before = SyncLog.objects(repository_full_name=repository_name).count()
            repo_stats_before = RepositoryStats.objects(repository_full_name=repository_name).count()
            
            self.stdout.write("MongoDB data before deletion:")
            self.stdout.write(f"  - Commits: {commits_before}")
            self.stdout.write(f"  - Sync logs: {sync_logs_before}")
            self.stdout.write(f"  - Repository stats: {repo_stats_before}")
            
            # Delete the repository (this should trigger cleanup)
            repo_name = repository.github_repo_name
            repository.delete()
            
            # Check MongoDB data after deletion
            commits_after = Commit.objects(repository_full_name=repository_name).count()
            sync_logs_after = SyncLog.objects(repository_full_name=repository_name).count()
            repo_stats_after = RepositoryStats.objects(repository_full_name=repository_name).count()
            
            self.stdout.write("MongoDB data after deletion:")
            self.stdout.write(f"  - Commits: {commits_after}")
            self.stdout.write(f"  - Sync logs: {sync_logs_after}")
            self.stdout.write(f"  - Repository stats: {repo_stats_after}")
            
            # Verify cleanup
            if commits_after == 0 and sync_logs_after == 0 and repo_stats_after == 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Repository "{repo_name}" deleted successfully with all MongoDB data cleaned up!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Repository deleted but some MongoDB data remains: {commits_after} commits, {sync_logs_after} sync logs, {repo_stats_after} repo stats')
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