"""
Management command to check for orphan aliases (aliases not associated with any developer).
"""

from django.core.management.base import BaseCommand
from analytics.models import DeveloperAlias, Developer
from collections import defaultdict


class Command(BaseCommand):
    help = 'Check for orphan aliases (aliases not associated with any developer)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--show-details',
            action='store_true',
            help='Show detailed information about orphan aliases',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Checking for orphan aliases...')
        )
        
        # Get all aliases
        all_aliases = DeveloperAlias.objects.all()
        total_aliases = all_aliases.count()
        
        # Find orphan aliases (developer is None)
        orphan_aliases = DeveloperAlias.objects.filter(developer=None)
        orphan_count = orphan_aliases.count()
        
        # Get grouped aliases
        grouped_aliases = DeveloperAlias.objects.filter(developer__ne=None)
        grouped_count = grouped_aliases.count()
        
        # Statistics
        self.stdout.write(f'\n📊 Alias Statistics:')
        self.stdout.write(f'  - Total aliases: {total_aliases}')
        self.stdout.write(f'  - Grouped aliases: {grouped_count}')
        self.stdout.write(f'  - Orphan aliases: {orphan_count}')
        self.stdout.write(f'  - Grouping rate: {(grouped_count/total_aliases)*100:.1f}%')
        
        if orphan_count > 0:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  Found {orphan_count} orphan aliases:')
            )
            
            if options['show_details']:
                # Group orphans by domain for better analysis
                domain_stats = defaultdict(list)
                for alias in orphan_aliases:
                    domain = alias.email.split('@')[1] if '@' in alias.email else 'unknown'
                    domain_stats[domain].append(alias)
                
                # Show orphans by domain
                for domain, aliases in sorted(domain_stats.items()):
                    self.stdout.write(f'\n📧 Domain: {domain} ({len(aliases)} aliases)')
                    for alias in aliases[:5]:  # Show first 5 per domain
                        self.stdout.write(f'  - {alias.name} ({alias.email}) - {alias.commit_count} commits')
                    if len(aliases) > 5:
                        self.stdout.write(f'  ... and {len(aliases) - 5} more')
                
                # Show top orphan aliases by commit count
                top_orphans = orphan_aliases.order_by('-commit_count')[:10]
                self.stdout.write(f'\n🔥 Top orphan aliases by commit count:')
                for alias in top_orphans:
                    self.stdout.write(f'  - {alias.name} ({alias.email}): {alias.commit_count} commits')
            else:
                self.stdout.write(f'  Use --show-details to see detailed information')
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ No orphan aliases found! All aliases are grouped.')
            )
        
        # Check for developers with many aliases
        developer_stats = defaultdict(int)
        for alias in grouped_aliases:
            if alias.developer:
                developer_stats[str(alias.developer.id)] += 1
        
        if developer_stats:
            max_aliases = max(developer_stats.values())
            avg_aliases = sum(developer_stats.values()) / len(developer_stats)
            
            self.stdout.write(f'\n👥 Developer grouping statistics:')
            self.stdout.write(f'  - Developers with aliases: {len(developer_stats)}')
            self.stdout.write(f'  - Average aliases per developer: {avg_aliases:.1f}')
            self.stdout.write(f'  - Max aliases per developer: {max_aliases}')
            
            # Show developers with most aliases
            top_developers = sorted(developer_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            self.stdout.write(f'\n🏆 Developers with most aliases:')
            for dev_id, alias_count in top_developers:
                developer = Developer.objects(id=dev_id).first()
                if developer:
                    self.stdout.write(f'  - {developer.primary_name} ({developer.primary_email}): {alias_count} aliases')
        
        # Summary
        if orphan_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'\n💡 Recommendation: Consider running group_developer_identities_task to group orphan aliases.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎉 All aliases are properly grouped!'
                )
            ) 