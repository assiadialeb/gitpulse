"""
Management command to test quality analysis during indexing
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from applications.models import Application
from analytics.quality_service import QualityAnalysisService
from analytics.git_sync_service import GitSyncService
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Test quality analysis during indexing for an application'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'application_id',
            type=int,
            help='Application ID to test'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID (optional, will use first user if not provided)'
        )
        parser.add_argument(
            '--sync-type',
            choices=['full', 'incremental'],
            default='incremental',
            help='Sync type (default: incremental)'
        )
        parser.add_argument(
            '--quality-only',
            action='store_true',
            help='Only run quality analysis on existing commits'
        )
    
    def handle(self, *args, **options):
        application_id = options['application_id']
        user_id = options['user_id']
        sync_type = options['sync_type']
        quality_only = options['quality_only']
        
        try:
            # Get or determine user
            if user_id:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.first()
                if not user:
                    raise CommandError("No users found in database")
                user_id = user.id
            
            # Get application
            try:
                application = Application.objects.get(id=application_id, owner_id=user_id)
            except Application.DoesNotExist:
                raise CommandError(f"Application {application_id} not found for user {user_id}")
            
            self.stdout.write(f"Testing quality analysis for application: {application.name}")
            self.stdout.write(f"User: {user.username}")
            self.stdout.write(f"Repositories: {application.repositories.count()}")
            
            if quality_only:
                # Only run quality analysis on existing commits
                self.stdout.write("Running quality analysis on existing commits...")
                quality_service = QualityAnalysisService()
                processed = quality_service.analyze_commits_for_application(application_id)
                self.stdout.write(
                    self.style.SUCCESS(f"Quality analysis completed: {processed} commits processed")
                )
            else:
                # Run full indexing with quality analysis
                self.stdout.write(f"Starting sync with quality analysis (type: {sync_type})...")
                sync_service = GitSyncService(user_id)
                
                results = sync_service.sync_application_repositories_with_progress(
                    application_id, sync_type
                )
                
                self.stdout.write("Sync results:")
                self.stdout.write(f"  Repositories synced: {results['repositories_synced']}")
                self.stdout.write(f"  New commits: {results['total_commits_new']}")
                self.stdout.write(f"  Updated commits: {results['total_commits_updated']}")
                self.stdout.write(f"  Total processed: {results['total_commits_processed']}")
                
                if results['errors']:
                    self.stdout.write(self.style.WARNING("Errors encountered:"))
                    for error in results['errors']:
                        self.stdout.write(f"  - {error}")
                else:
                    self.stdout.write(
                        self.style.SUCCESS("Sync completed successfully with quality analysis")
                    )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error during quality indexing test: {e}")
            )
            raise CommandError(str(e)) 