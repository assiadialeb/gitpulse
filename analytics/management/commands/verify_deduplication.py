"""
Management command to verify that alias deduplication worked correctly.
"""

from django.core.management.base import BaseCommand
from analytics.models import DeveloperAlias
from collections import defaultdict


class Command(BaseCommand):
    help = 'Verify that alias deduplication worked correctly'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Verifying alias deduplication...')
        )
        
        # Group aliases by email
        email_groups = defaultdict(list)
        all_aliases = DeveloperAlias.objects.all()
        
        for alias in all_aliases:
            email_groups[alias.email.lower()].append(alias)
        
        # Find any remaining duplicates
        remaining_duplicates = {
            email: aliases for email, aliases in email_groups.items() 
            if len(aliases) > 1
        }
        
        if remaining_duplicates:
            self.stdout.write(
                self.style.ERROR(
                    f'Found {len(remaining_duplicates)} email addresses with remaining duplicates:'
                )
            )
            for email, aliases in remaining_duplicates.items():
                self.stdout.write(f'\nEmail: {email}')
                for alias in aliases:
                    self.stdout.write(f'  - {alias.name} (ID: {alias.id})')
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ No remaining duplicates found!')
            )
        
        # Show statistics
        total_aliases = len(all_aliases)
        unique_emails = len(email_groups)
        
        self.stdout.write(f'\n📊 Statistics:')
        self.stdout.write(f'  - Total aliases: {total_aliases}')
        self.stdout.write(f'  - Unique emails: {unique_emails}')
        self.stdout.write(f'  - Average aliases per email: {total_aliases / unique_emails:.2f}')
        
        # Show some examples of merged names
        self.stdout.write(f'\n📝 Examples of merged names:')
        examples_shown = 0
        for alias in all_aliases:
            if ' | ' in alias.name and examples_shown < 10:
                self.stdout.write(f'  - {alias.email}: {alias.name}')
                examples_shown += 1
        
        # Check for aliases with multiple names
        multi_name_aliases = [a for a in all_aliases if ' | ' in a.name]
        self.stdout.write(f'\n🔗 Aliases with multiple names: {len(multi_name_aliases)}')
        
        # Show distribution of name counts
        name_count_distribution = defaultdict(int)
        for alias in all_aliases:
            name_count = len(alias.name.split(' | '))
            name_count_distribution[name_count] += 1
        
        self.stdout.write(f'\n📈 Name count distribution:')
        for count, frequency in sorted(name_count_distribution.items()):
            self.stdout.write(f'  - {count} name(s): {frequency} aliases') 