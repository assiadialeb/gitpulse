"""
Management command to manually index repositories
"""
from django.core.management.base import BaseCommand
from applications.models import Application
from analytics.git_sync_service import GitSyncService
from analytics.github_service import GitHubAPIError
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manually index repositories for an application'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to index')
        parser.add_argument('--skip-lfs', action='store_true', 
                          help='Skip repositories that have LFS issues')
        parser.add_argument('--sync-type', choices=['full', 'incremental'], 
                          default='full', help='Type of sync to perform')
        parser.add_argument('--repo', type=str, 
                          help='Index only a specific repository (format: owner/repo)')

    def handle(self, *args, **options):
        application_id = options['application_id']
        skip_lfs = options['skip_lfs']
        sync_type = options['sync_type']
        specific_repo = options.get('repo')
        
        try:
            application = Application.objects.get(id=application_id)
        except Application.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Application {application_id} not found')
            )
            return

        self.stdout.write(f'Starting {sync_type} indexing for application: {application.name}')
        if skip_lfs:
            self.stdout.write('LFS repositories will be skipped on error')

        # Initialize sync service
        try:
            sync_service = GitSyncService(application.owner_id)
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to initialize sync service: {e}')
            )
            return

        # Get repositories to index
        repositories = application.repositories.all()
        if specific_repo:
            repositories = repositories.filter(github_repo_name=specific_repo)
            if not repositories.exists():
                self.stdout.write(
                    self.style.ERROR(f'Repository {specific_repo} not found in application')
                )
                return

        total_repos = repositories.count()
        self.stdout.write(f'Found {total_repos} repositories to index')

        # Index each repository
        success_count = 0
        error_count = 0
        skipped_count = 0

        for i, repo in enumerate(repositories, 1):
            repo_name = repo.github_repo_name
            self.stdout.write(f'[{i}/{total_repos}] Indexing {repo_name}...')

            try:
                # Get repo URL
                repo_url = getattr(repo, 'github_repo_url', None)
                if not repo_url:
                    repo_url = f"https://github.com/{repo_name}.git"

                # Attempt to sync repository
                result = sync_service.sync_repository(
                    repo_name, repo_url, application_id, sync_type
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✅ Success: {result["commits_new"]} new commits, '
                        f'{result["commits_updated"]} updated'
                    )
                )
                success_count += 1

            except Exception as e:
                error_msg = str(e)
                
                # Check if it's an LFS error
                is_lfs_error = any(lfs_keyword in error_msg.lower() for lfs_keyword in [
                    'git-lfs', 'lfs', 'filter-process', 'smudge'
                ])

                if is_lfs_error and skip_lfs:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️  Skipped (LFS issue): {repo_name}')
                    )
                    skipped_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Failed: {error_msg}')
                    )
                    error_count += 1

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('INDEXING SUMMARY')
        self.stdout.write('='*50)
        self.stdout.write(f'Total repositories: {total_repos}')
        self.stdout.write(
            self.style.SUCCESS(f'Successful: {success_count}')
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Failed: {error_count}')
            )
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Skipped (LFS): {skipped_count}')
            )

        if success_count == total_repos:
            self.stdout.write(
                self.style.SUCCESS('\n🎉 All repositories indexed successfully!')
            )
        elif success_count > 0:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  Partial success: {success_count}/{total_repos} repositories indexed')
            )
        else:
            self.stdout.write(
                self.style.ERROR('\n❌ No repositories were successfully indexed')
            )