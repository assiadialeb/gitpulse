"""
Management command to fix duplicate developer groups
"""
from django.core.management.base import BaseCommand
from analytics.analytics_service import AnalyticsService
from analytics.models import DeveloperGroup, DeveloperAlias
from collections import defaultdict


class Command(BaseCommand):
    help = 'Fix duplicate developer groups by merging them properly'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to fix groups for')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        application_id = options['application_id']
        dry_run = options['dry_run']
        
        self.stdout.write(f"Fixing duplicate groups for application {application_id}")
        
        try:
            # Get all groups for this application
            groups = DeveloperGroup.objects.filter(application_id=application_id)
            
            # Group by primary email to find duplicates
            email_groups = defaultdict(list)
            for group in groups:
                email_groups[group.primary_email.lower()].append(group)
            
            # Find groups with same primary email
            duplicates_found = False
            for email, group_list in email_groups.items():
                if len(group_list) > 1:
                    duplicates_found = True
                    self.stdout.write(f"\n🔍 Found {len(group_list)} groups with email: {email}")
                    
                    for i, group in enumerate(group_list):
                        aliases = DeveloperAlias.objects.filter(group=group)
                        self.stdout.write(f"  Group {i+1}: {group.primary_name} ({len(aliases)} aliases)")
                        for alias in aliases:
                            self.stdout.write(f"    - {alias.name} ({alias.email}) - {alias.commit_count} commits")
                    
                    if not dry_run:
                        # Merge all groups into the first one (keep the one with most commits)
                        primary_group = max(group_list, key=lambda g: sum(a.commit_count for a in DeveloperAlias.objects.filter(group=g)))
                        
                        self.stdout.write(f"  📝 Merging into: {primary_group.primary_name}")
                        
                        # Move all aliases from other groups to the primary group
                        for group in group_list:
                            if group != primary_group:
                                aliases = DeveloperAlias.objects.filter(group=group)
                                for alias in aliases:
                                    # Check if alias already exists in primary group
                                    existing = DeveloperAlias.objects.filter(
                                        group=primary_group,
                                        email=alias.email,
                                        name=alias.name
                                    ).first()
                                    
                                    if existing:
                                        # Update existing alias
                                        existing.commit_count += alias.commit_count
                                        existing.last_seen = max(existing.last_seen, alias.last_seen)
                                        existing.save()
                                        alias.delete()
                                    else:
                                        # Move alias to primary group
                                        alias.group = primary_group
                                        alias.save()
                                
                                # Delete the duplicate group
                                group.delete()
                        
                        self.stdout.write(f"  ✅ Merged {len(group_list)-1} duplicate groups")
            
            if not duplicates_found:
                self.stdout.write("✅ No duplicate groups found")
            
            # Re-run grouping to ensure everything is properly grouped
            if not dry_run:
                self.stdout.write("\n🔄 Re-running developer grouping...")
                analytics = AnalyticsService(application_id)
                results = analytics.group_developers()
                self.stdout.write(f"✅ Re-grouping completed: {results['groups_created']} groups")
            
            self.stdout.write("\n✅ Duplicate group fixing completed!")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            raise 