"""
Management command to cleanup auto-created developer groups
"""
from django.core.management.base import BaseCommand
from analytics.models import DeveloperGroup, DeveloperAlias


class Command(BaseCommand):
    help = 'Remove all auto-created developer groups and keep only manual groups'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to cleanup groups for')
        parser.add_argument('--force', action='store_true', help='Force cleanup without confirmation')

    def handle(self, *args, **options):
        application_id = options['application_id']
        force = options['force']
        
        self.stdout.write(f"Cleaning up auto-created groups for application {application_id}")
        
        # Count auto-created groups
        auto_groups = DeveloperGroup.objects.filter(
            application_id=application_id,
            is_auto_grouped=True
        )
        
        auto_groups_count = auto_groups.count()
        
        if auto_groups_count == 0:
            self.stdout.write("✓ No auto-created groups found")
            return
        
        self.stdout.write(f"Found {auto_groups_count} auto-created groups")
        
        if not force:
            confirm = input("Do you want to delete all auto-created groups? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Operation cancelled")
                return
        
        # Delete auto-created groups and their aliases
        deleted_groups = 0
        deleted_aliases = 0
        
        for group in auto_groups:
            # Count aliases to be deleted
            aliases_count = DeveloperAlias.objects.filter(group=group).count()
            deleted_aliases += aliases_count
            
            # Delete aliases first (due to foreign key constraint)
            DeveloperAlias.objects.filter(group=group).delete()
            
            # Delete the group
            group.delete()
            deleted_groups += 1
            
            self.stdout.write(f"Deleted group '{group.primary_name}' with {aliases_count} aliases")
        
        self.stdout.write(f"\n✅ Cleanup completed!")
        self.stdout.write(f"✓ Deleted {deleted_groups} auto-created groups")
        self.stdout.write(f"✓ Deleted {deleted_aliases} developer aliases")
        
        # Show remaining manual groups
        manual_groups = DeveloperGroup.objects.filter(
            application_id=application_id,
            is_auto_grouped=False
        )
        
        if manual_groups.count() > 0:
            self.stdout.write(f"\nRemaining manual groups: {manual_groups.count()}")
            for group in manual_groups:
                aliases_count = DeveloperAlias.objects.filter(group=group).count()
                self.stdout.write(f"  - {group.primary_name} ({group.primary_email}) - {aliases_count} aliases")
        else:
            self.stdout.write("\nNo manual groups remaining") 