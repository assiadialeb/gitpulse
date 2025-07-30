"""
Test script to simulate disassociating an alias from a developer.
"""

from django.core.management.base import BaseCommand
from analytics.models import DeveloperAlias, Developer


class Command(BaseCommand):
    help = 'Test disassociating an alias from a developer'

    def add_arguments(self, parser):
        parser.add_argument(
            '--developer-id',
            type=str,
            help='Developer ID to test with',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Testing alias disassociation...')
        )
        
        # Find a developer with multiple aliases
        developers_with_aliases = []
        for developer in Developer.objects.all():
            alias_count = DeveloperAlias.objects.filter(developer=developer).count()
            if alias_count > 1:
                developers_with_aliases.append((developer, alias_count))
        
        if not developers_with_aliases:
            self.stdout.write('No developers with multiple aliases found!')
            return
        
        # Choose the first developer with most aliases
        test_developer, alias_count = max(developers_with_aliases, key=lambda x: x[1])
        
        self.stdout.write(f'Testing with developer: {test_developer.primary_name} ({test_developer.primary_email})')
        self.stdout.write(f'This developer has {alias_count} aliases')
        
        # Show current aliases
        aliases = DeveloperAlias.objects.filter(developer=test_developer)
        self.stdout.write(f'\nCurrent aliases:')
        for alias in aliases:
            self.stdout.write(f'  - {alias.name} ({alias.email}) - {alias.commit_count} commits')
        
        # Choose the first alias to disassociate
        test_alias = aliases.first()
        if not test_alias:
            self.stdout.write('No aliases found for this developer!')
            return
        
        self.stdout.write(f'\n🎯 Will disassociate: {test_alias.name} ({test_alias.email})')
        
        # Check orphan count before
        orphan_count_before = DeveloperAlias.objects.filter(developer=None).count()
        self.stdout.write(f'Orphan aliases before: {orphan_count_before}')
        
        # Disassociate the alias
        test_alias.developer = None
        test_alias.save()
        
        # Check orphan count after
        orphan_count_after = DeveloperAlias.objects.filter(developer=None).count()
        self.stdout.write(f'Orphan aliases after: {orphan_count_after}')
        
        # Show the orphan alias
        orphan_aliases = DeveloperAlias.objects.filter(developer=None)
        self.stdout.write(f'\n📋 Orphan aliases:')
        for alias in orphan_aliases:
            self.stdout.write(f'  - {alias.name} ({alias.email}) - {alias.commit_count} commits')
        
        # Reassociate the alias (cleanup)
        test_alias.developer = test_developer
        test_alias.save()
        
        self.stdout.write(f'\n✅ Test completed! Alias has been reassociated.')
        self.stdout.write(f'Final orphan count: {DeveloperAlias.objects.filter(developer=None).count()}') 