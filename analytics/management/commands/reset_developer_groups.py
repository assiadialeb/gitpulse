"""
Management command to reset all developer groups and start fresh
"""
from django.core.management.base import BaseCommand
from analytics.models import DeveloperGroup, DeveloperAlias


class Command(BaseCommand):
    help = 'Reset all developer groups and aliases to start fresh'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force reset without confirmation')

    def handle(self, *args, **options):
        force = options['force']
        
        self.stdout.write("Resetting all developer groups and aliases...")
        
        # Count existing groups and aliases
        groups_count = DeveloperGroup.objects.count()
        aliases_count = DeveloperAlias.objects.count()
        
        if groups_count == 0 and aliases_count == 0:
            self.stdout.write("✓ No groups or aliases found - nothing to reset")
            return
        
        self.stdout.write(f"Found {groups_count} groups and {aliases_count} aliases")
        
        if not force:
            confirm = input("Do you want to delete ALL groups and aliases? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Operation cancelled")
                return
        
        # Delete all aliases first (due to foreign key constraint)
        deleted_aliases = DeveloperAlias.objects.count()
        DeveloperAlias.objects.all().delete()
        
        # Delete all groups
        deleted_groups = DeveloperGroup.objects.count()
        DeveloperGroup.objects.all().delete()
        
        self.stdout.write(f"\n✅ Reset completed!")
        self.stdout.write(f"✓ Deleted {deleted_groups} developer groups")
        self.stdout.write(f"✓ Deleted {deleted_aliases} developer aliases")
        self.stdout.write(f"\nAll developer groups have been reset. You can now create new groups manually.") 