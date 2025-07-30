"""
Management command to deduplicate developer aliases by email.

This command merges duplicate aliases that have the same email but different names,
keeping all names in a list and using email as the unique identifier.
"""

from django.core.management.base import BaseCommand
from analytics.models import DeveloperAlias, Developer
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Deduplicate developer aliases by email, keeping all names'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force the operation even if there are potential issues',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('Starting alias deduplication by email...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Group aliases by email
        email_groups = defaultdict(list)
        all_aliases = DeveloperAlias.objects.all()
        
        for alias in all_aliases:
            email_groups[alias.email.lower()].append(alias)
        
        # Find groups with multiple aliases (duplicates)
        duplicates = {
            email: aliases for email, aliases in email_groups.items() 
            if len(aliases) > 1
        }
        
        if not duplicates:
            self.stdout.write(
                self.style.SUCCESS('No duplicate aliases found!')
            )
            return
        
        self.stdout.write(
            f'Found {len(duplicates)} email addresses with duplicate aliases:'
        )
        
        # Show what will be merged
        for email, aliases in duplicates.items():
            self.stdout.write(f'\nEmail: {email}')
            for alias in aliases:
                self.stdout.write(f'  - {alias.name} (ID: {alias.id})')
        
        if not force and not dry_run:
            response = input('\nProceed with deduplication? (y/N): ')
            if response.lower() != 'y':
                self.stdout.write('Operation cancelled.')
                return
        
        # Perform the deduplication
        merged_count = 0
        deleted_count = 0
        
        for email, aliases in duplicates.items():
            if len(aliases) == 0:
                continue
                
            # Sort aliases by commit_count (keep the one with most commits as primary)
            aliases.sort(key=lambda x: x.commit_count, reverse=True)
            primary_alias = aliases[0]
            secondary_aliases = aliases[1:]
            
            # Collect all unique names
            all_names = [primary_alias.name]
            for alias in secondary_aliases:
                if alias.name not in all_names:
                    all_names.append(alias.name)
            
            # Update primary alias with all names
            if not dry_run:
                # For now, we'll keep the primary name as 'name' and add others to a new field
                # In a future migration, we can add a 'names' field to the model
                primary_alias.name = ' | '.join(all_names)
                
                # Merge commit counts and dates
                total_commits = sum(alias.commit_count for alias in aliases)
                first_seen = min(alias.first_seen for alias in aliases)
                last_seen = max(alias.last_seen for alias in aliases)
                
                primary_alias.commit_count = total_commits
                primary_alias.first_seen = first_seen
                primary_alias.last_seen = last_seen
                primary_alias.save()
                
                # Delete secondary aliases
                for alias in secondary_aliases:
                    alias.delete()
                    deleted_count += 1
            
            merged_count += 1
            
            if dry_run:
                self.stdout.write(
                    f'Would merge {len(aliases)} aliases for {email} into: {primary_alias.name}'
                )
            else:
                self.stdout.write(
                    f'Merged {len(aliases)} aliases for {email} into: {primary_alias.name}'
                )
        
        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY RUN SUMMARY: Would merge {merged_count} email groups, '
                    f'deleting {deleted_count} duplicate aliases'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSUCCESS: Merged {merged_count} email groups, '
                    f'deleted {deleted_count} duplicate aliases'
                )
            )
            
            # Verify no more duplicates
            remaining_duplicates = self._check_for_duplicates()
            if remaining_duplicates:
                self.stdout.write(
                    self.style.WARNING(
                        f'Warning: {len(remaining_duplicates)} email addresses still have duplicates'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('All duplicates have been resolved!')
                )
    
    def _check_for_duplicates(self):
        """Check if there are still duplicate aliases by email"""
        email_groups = defaultdict(list)
        all_aliases = DeveloperAlias.objects.all()
        
        for alias in all_aliases:
            email_groups[alias.email.lower()].append(alias)
        
        return {
            email: aliases for email, aliases in email_groups.items() 
            if len(aliases) > 1
        } 