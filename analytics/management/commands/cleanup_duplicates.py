from django.core.management.base import BaseCommand, CommandError
from collections import defaultdict
from analytics.models import Developer, DeveloperAlias


class Command(BaseCommand):
    help = 'Clean up duplicates in Developer and DeveloperAlias collections'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually apply the changes (use with caution!)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run'] or not options['apply']
        
        if not options['dry_run'] and not options['apply']:
            self.stdout.write(
                self.style.ERROR('Please specify either --dry-run or --apply')
            )
            self.stdout.write('  --dry-run: Show what would be done without making changes')
            self.stdout.write('  --apply: Actually apply the changes (use with caution!)')
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🧹 DRY RUN MODE - No changes will be made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('🧹 APPLYING CHANGES - This will modify your database!')
            )
        
        self.stdout.write('=' * 60)
        
        # Show initial statistics
        self.show_statistics()
        
        self.stdout.write('\n' + '=' * 60)
        
        # Clean up duplicates
        aliases_merged, aliases_deleted = self.cleanup_developer_aliases(dry_run)
        developers_merged, developers_deleted = self.cleanup_developers(dry_run)
        orphan_count = self.fix_orphan_aliases(dry_run)
        
        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write('📊 Dry Run Summary:')
            self.stdout.write(f'  📧 Aliases: Would merge {aliases_merged} groups, would delete {aliases_deleted}')
            self.stdout.write(f'  👥 Developers: Would merge {developers_merged} groups, would delete {developers_deleted}')
            self.stdout.write(f'  🚫 Orphan aliases: Would fix {orphan_count}')
            self.stdout.write('\n💡 To apply these changes, run with --apply')
        else:
            self.stdout.write('📊 Cleanup Summary:')
            self.stdout.write(f'  📧 Aliases: {aliases_merged} groups merged, {aliases_deleted} deleted')
            self.stdout.write(f'  👥 Developers: {developers_merged} groups merged, {developers_deleted} deleted')
            self.stdout.write(f'  🚫 Orphan aliases fixed: {orphan_count}')
        
        self.stdout.write('\n' + '=' * 60)
        
        # Show final statistics
        self.show_statistics()
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS('\n✅ Dry run completed! Review the changes above.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ Cleanup completed!')
            )

    def cleanup_developer_aliases(self, dry_run=True):
        """Clean up duplicate DeveloperAlias entries"""
        self.stdout.write('🔍 Cleaning up DeveloperAlias duplicates...')
        
        # Find duplicates by email
        email_groups = defaultdict(list)
        for alias in DeveloperAlias.objects.all():
            email_groups[alias.email.lower()].append(alias)
        
        aliases_merged = 0
        aliases_deleted = 0
        
        for email, aliases in email_groups.items():
            if len(aliases) > 1:
                self.stdout.write(f'  📧 Found {len(aliases)} aliases for email: {email}')
                
                # Sort by commit_count (keep the one with most commits)
                aliases.sort(key=lambda x: x.commit_count, reverse=True)
                primary_alias = aliases[0]
                
                # Merge names from all aliases
                all_names = set()
                for alias in aliases:
                    if alias.name:
                        all_names.add(alias.name)
                
                if dry_run:
                    self.stdout.write(f'    🔍 Would merge into: {primary_alias.name} ({primary_alias.email})')
                    self.stdout.write(f'    🔍 Would combine names: {" | ".join(sorted(all_names))}')
                    self.stdout.write(f'    🔍 Would delete {len(aliases) - 1} aliases')
                else:
                    # Update primary alias with combined name
                    if len(all_names) > 1:
                        primary_alias.name = " | ".join(sorted(all_names))
                    
                    # Update commit count and dates
                    total_commits = sum(alias.commit_count for alias in aliases)
                    first_seen = min(alias.first_seen for alias in aliases)
                    last_seen = max(alias.last_seen for alias in aliases)
                    
                    primary_alias.commit_count = total_commits
                    primary_alias.first_seen = first_seen
                    primary_alias.last_seen = last_seen
                    primary_alias.save()
                    
                    # Delete other aliases
                    for alias in aliases[1:]:
                        # If this alias was linked to a developer, update the primary alias
                        if alias.developer and not primary_alias.developer:
                            primary_alias.developer = alias.developer
                            primary_alias.save()
                        
                        alias.delete()
                        aliases_deleted += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'    ✅ Merged into: {primary_alias.name} ({primary_alias.email})')
                    )
                
                aliases_merged += 1
        
        if dry_run:
            self.stdout.write(f'  📊 Would merge {aliases_merged} groups, would delete {aliases_deleted} aliases')
        else:
            self.stdout.write(f'  📊 Results: {aliases_merged} groups merged, {aliases_deleted} aliases deleted')
        
        return aliases_merged, aliases_deleted

    def cleanup_developers(self, dry_run=True):
        """Clean up duplicate Developer entries"""
        self.stdout.write('🔍 Cleaning up Developer duplicates...')
        
        # Find duplicates by primary_email
        email_groups = defaultdict(list)
        for developer in Developer.objects.all():
            email_groups[developer.primary_email.lower()].append(developer)
        
        developers_merged = 0
        developers_deleted = 0
        
        for email, developers in email_groups.items():
            if len(developers) > 1:
                self.stdout.write(f'  📧 Found {len(developers)} developers for email: {email}')
                
                # Sort by confidence_score (keep the one with highest confidence)
                developers.sort(key=lambda x: x.confidence_score, reverse=True)
                primary_developer = developers[0]
                
                # Merge names from all developers
                all_names = set()
                for dev in developers:
                    if dev.primary_name:
                        all_names.add(dev.primary_name)
                
                if dry_run:
                    self.stdout.write(f'    🔍 Would merge into: {primary_developer.primary_name} ({primary_developer.primary_email})')
                    self.stdout.write(f'    🔍 Would combine names: {" | ".join(sorted(all_names))}')
                    self.stdout.write(f'    🔍 Would delete {len(developers) - 1} developers')
                else:
                    # Update primary developer with combined name
                    if len(all_names) > 1:
                        primary_developer.primary_name = " | ".join(sorted(all_names))
                    
                    # Update confidence score
                    max_confidence = max(dev.confidence_score for dev in developers)
                    primary_developer.confidence_score = max_confidence
                    primary_developer.save()
                    
                    # Move all aliases to primary developer
                    for dev in developers[1:]:
                        # Move aliases to primary developer
                        for alias in DeveloperAlias.objects.filter(developer=dev):
                            alias.developer = primary_developer
                            alias.save()
                        
                        dev.delete()
                        developers_deleted += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'    ✅ Merged into: {primary_developer.primary_name} ({primary_developer.primary_email})')
                    )
                
                developers_merged += 1
        
        if dry_run:
            self.stdout.write(f'  📊 Would merge {developers_merged} groups, would delete {developers_deleted} developers')
        else:
            self.stdout.write(f'  📊 Results: {developers_merged} groups merged, {developers_deleted} developers deleted')
        
        return developers_merged, developers_deleted

    def fix_orphan_aliases(self, dry_run=True):
        """Fix aliases that are linked to non-existent developers"""
        self.stdout.write('🔍 Fixing orphan aliases...')
        
        orphan_count = 0
        for alias in DeveloperAlias.objects.all():
            if alias.developer:
                try:
                    # Try to get the developer - if it doesn't exist, this will fail
                    Developer.objects.get(id=alias.developer.id)
                except Developer.DoesNotExist:
                    self.stdout.write(f'  🚨 Found orphan alias: {alias.name} ({alias.email})')
                    if not dry_run:
                        alias.developer = None
                        alias.save()
                    orphan_count += 1
        
        if dry_run:
            self.stdout.write(f'  📊 Would fix {orphan_count} orphan aliases')
        else:
            self.stdout.write(f'  📊 Results: {orphan_count} orphan aliases fixed')
        
        return orphan_count

    def show_statistics(self):
        """Show current statistics"""
        self.stdout.write('\n📊 Current Statistics:')
        self.stdout.write(f'  👥 Total Developers: {Developer.objects.count()}')
        self.stdout.write(f'  📧 Total Aliases: {DeveloperAlias.objects.count()}')
        self.stdout.write(f'  🔗 Linked Aliases: {DeveloperAlias.objects.filter(developer__ne=None).count()}')
        self.stdout.write(f'  🚫 Unlinked Aliases: {DeveloperAlias.objects.filter(developer=None).count()}')
        
        # Show some examples of duplicates
        self.stdout.write('\n🔍 Checking for potential duplicates...')
        
        # Check DeveloperAlias duplicates
        email_counts = {}
        for alias in DeveloperAlias.objects.all():
            email = alias.email.lower()
            email_counts[email] = email_counts.get(email, 0) + 1
        
        duplicate_emails = {email: count for email, count in email_counts.items() if count > 1}
        if duplicate_emails:
            self.stdout.write(f'  📧 Found {len(duplicate_emails)} emails with multiple aliases:')
            for email, count in list(duplicate_emails.items())[:5]:  # Show first 5
                self.stdout.write(f'    - {email}: {count} aliases')
        else:
            self.stdout.write('  ✅ No duplicate emails found in aliases')
        
        # Check Developer duplicates
        dev_email_counts = {}
        for dev in Developer.objects.all():
            email = dev.primary_email.lower()
            dev_email_counts[email] = dev_email_counts.get(email, 0) + 1
        
        duplicate_dev_emails = {email: count for email, count in dev_email_counts.items() if count > 1}
        if duplicate_dev_emails:
            self.stdout.write(f'  👥 Found {len(duplicate_dev_emails)} emails with multiple developers:')
            for email, count in list(duplicate_dev_emails.items())[:5]:  # Show first 5
                self.stdout.write(f'    - {email}: {count} developers')
        else:
            self.stdout.write('  ✅ No duplicate emails found in developers') 