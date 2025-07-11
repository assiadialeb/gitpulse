"""
Django management command to test the sync system
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from applications.models import Application, ApplicationRepository
from analytics.sync_service import SyncService
from analytics.models import Commit, SyncLog, RepositoryStats
from analytics.tasks import manual_sync_application
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test the commit synchronization system'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--application-id',
            type=int,
            help='Application ID to sync (required)',
            required=True
        )
        parser.add_argument(
            '--sync-type',
            type=str,
            choices=['full', 'incremental'],
            default='incremental',
            help='Type of sync to perform'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run sync asynchronously using Django-Q'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show stats after sync'
        )
    
    def handle(self, *args, **options):
        application_id = options['application_id']
        sync_type = options['sync_type']
        use_async = options['async']
        show_stats = options['stats']
        
        self.stdout.write(
            self.style.SUCCESS(f'Testing sync for application {application_id}')
        )
        
        try:
            # Get application and validate
            application = Application.objects.get(id=application_id)
            repositories = ApplicationRepository.objects.filter(application=application)
            
            if not repositories.exists():
                self.stdout.write(
                    self.style.ERROR(f'No repositories found for application {application_id}')
                )
                return
            
            self.stdout.write(f'Application: {application.name}')
            self.stdout.write(f'Owner: {application.owner.username}')
            self.stdout.write(f'Repositories: {repositories.count()}')
            
            for repo in repositories:
                self.stdout.write(f'  - {repo.github_repo_name}')
            
            # Run sync
            if use_async:
                self.stdout.write('Starting async sync...')
                task_id = manual_sync_application(application_id, sync_type)
                self.stdout.write(
                    self.style.SUCCESS(f'Async task scheduled: {task_id}')
                )
                self.stdout.write('Check Django-Q dashboard for progress')
            else:
                self.stdout.write(f'Starting {sync_type} sync...')
                sync_service = SyncService(application.owner_id)
                results = sync_service.sync_application_repositories(application_id, sync_type)
                
                self.stdout.write(self.style.SUCCESS('Sync completed!'))
                self.stdout.write(f'Results: {results}')
            
            # Show stats if requested
            if show_stats and not use_async:
                self._show_stats(application_id)
                
        except Application.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Application {application_id} not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Sync failed: {str(e)}')
            )
            logger.exception("Sync test failed")
    
    def _show_stats(self, application_id):
        """Show statistics after sync"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write('SYNC STATISTICS')
        self.stdout.write('='*50)
        
        # Repository stats
        repo_stats = RepositoryStats.objects.filter(application_id=application_id)
        for stat in repo_stats:
            self.stdout.write(f'\nRepository: {stat.repository_full_name}')
            self.stdout.write(f'  Total commits: {stat.total_commits}')
            self.stdout.write(f'  Total authors: {stat.total_authors}')
            self.stdout.write(f'  Total additions: {stat.total_additions}')
            self.stdout.write(f'  Total deletions: {stat.total_deletions}')
            self.stdout.write(f'  Last sync: {stat.last_sync_at}')
            self.stdout.write(f'  Last commit: {stat.last_commit_date}')
        
        # Recent sync logs
        recent_logs = SyncLog.objects.filter(application_id=application_id).order_by('-started_at')[:5]
        self.stdout.write('\nRecent sync logs:')
        for log in recent_logs:
            status_color = self.style.SUCCESS if log.status == 'completed' else self.style.ERROR
            self.stdout.write(f'  {log.started_at} - {status_color(log.status)} - {log.repository_full_name}')
            if log.status == 'completed':
                self.stdout.write(f'    New: {log.commits_new}, Updated: {log.commits_updated}, Skipped: {log.commits_skipped}')
            elif log.error_message:
                self.stdout.write(f'    Error: {log.error_message}')
        
        # Total commits count
        total_commits = Commit.objects.filter(application_id=application_id).count()
        self.stdout.write(f'\nTotal commits in MongoDB: {total_commits}')
        
        # Recent commits
        recent_commits = Commit.objects.filter(application_id=application_id)\
                                     .order_by('-authored_date')[:3]
        self.stdout.write('\nMost recent commits:')
        for commit in recent_commits:
            message_short = commit.message[:50] + '...' if len(commit.message) > 50 else commit.message
            self.stdout.write(f'  {commit.authored_date} - {commit.author_name}: {message_short}')
        
        self.stdout.write('='*50) 