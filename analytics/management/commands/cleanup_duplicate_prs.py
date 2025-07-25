from django.core.management.base import BaseCommand
from analytics.models import PullRequest

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up duplicate Pull Requests and ensure data integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--app-id',
            type=int,
            help='Clean up duplicates for a specific application only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        app_id = options.get('app_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get applications to process
        if app_id:
            applications = Application.objects.filter(id=app_id)
            self.stdout.write(f'Processing application {app_id} only')
        else:
            applications = Application.objects.all()
            self.stdout.write(f'Processing all {applications.count()} applications')

        total_duplicates_removed = 0
        total_prs_kept = 0

        for app in applications:
            self.stdout.write(f'\nProcessing application {app.id} ({app.name})')
            
            # Get all PRs for this application
            prs = PullRequest.objects(application_id=app.id)
            total_prs = prs.count()
            
            if total_prs == 0:
                self.stdout.write(f'  No PRs found for app {app.id}')
                continue

            self.stdout.write(f'  Found {total_prs} PRs')

            # Group PRs by unique key (app_id, repo, number)
            pr_groups = {}
            for pr in prs:
                key = (pr.application_id, pr.repository_full_name, pr.number)
                if key not in pr_groups:
                    pr_groups[key] = []
                pr_groups[key].append(pr)

            # Find duplicates
            duplicates_found = 0
            prs_to_keep = []
            prs_to_delete = []

            for key, pr_list in pr_groups.items():
                if len(pr_list) > 1:
                    duplicates_found += len(pr_list) - 1
                    
                    # Keep the most recent one (based on updated_at or created_at)
                    pr_list.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
                    prs_to_keep.append(pr_list[0])
                    prs_to_delete.extend(pr_list[1:])
                    
                    self.stdout.write(f'    Duplicate found: {pr_list[0].repository_full_name}#{pr_list[0].number} - keeping most recent, removing {len(pr_list)-1} duplicates')
                else:
                    prs_to_keep.append(pr_list[0])

            if duplicates_found > 0:
                self.stdout.write(f'  Found {duplicates_found} duplicates to remove')
                
                if not dry_run:
                    # Delete duplicates
                    for pr in prs_to_delete:
                        pr.delete()
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  Removed {len(prs_to_delete)} duplicate PRs')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'  Would remove {len(prs_to_delete)} duplicate PRs')
                    )
                
                total_duplicates_removed += len(prs_to_delete)
                total_prs_kept += len(prs_to_keep)
            else:
                self.stdout.write(f'  No duplicates found')
                total_prs_kept += total_prs

        # Summary
        self.stdout.write(f'\n{"="*50}')
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN SUMMARY: Would remove {total_duplicates_removed} duplicate PRs, keep {total_prs_kept} PRs')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'CLEANUP COMPLETED: Removed {total_duplicates_removed} duplicate PRs, kept {total_prs_kept} PRs')
            )

        # Verify no duplicates remain
        if not dry_run:
            self.stdout.write('\nVerifying no duplicates remain...')
            for app in applications:
                prs = PullRequest.objects(application_id=app.id)
                pr_groups = {}
                for pr in prs:
                    key = (pr.application_id, pr.repository_full_name, pr.number)
                    if key not in pr_groups:
                        pr_groups[key] = []
                    pr_groups[key].append(pr)
                
                remaining_duplicates = sum(1 for pr_list in pr_groups.values() if len(pr_list) > 1)
                if remaining_duplicates > 0:
                    self.stdout.write(
                        self.style.ERROR(f'  WARNING: {remaining_duplicates} duplicate groups still exist for app {app.id}')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'  App {app.id}: No duplicates remaining')
                    ) 