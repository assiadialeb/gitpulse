"""
Management command to manage orphan aliases (aliases not associated with any developer).
"""

from django.core.management.base import BaseCommand
from analytics.models import DeveloperAlias, Developer
from collections import defaultdict


class Command(BaseCommand):
    help = 'Manage orphan aliases - view and potentially reassign them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all orphan aliases',
        )
        parser.add_argument(
            '--reassign',
            action='store_true',
            help='Attempt to automatically reassign orphan aliases to existing developers',
        )
        parser.add_argument(
            '--create-developers',
            action='store_true',
            help='Create new developers for orphan aliases that cannot be reassigned',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Managing orphan aliases...')
        )
        
        # Get orphan aliases
        orphan_aliases = DeveloperAlias.objects.filter(developer=None)
        orphan_count = orphan_aliases.count()
        
        if orphan_count == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ No orphan aliases found!')
            )
            return
        
        self.stdout.write(f'Found {orphan_count} orphan aliases')
        
        if options['list']:
            self._list_orphan_aliases(orphan_aliases)
        
        if options['reassign']:
            self._reassign_orphan_aliases(orphan_aliases)
        
        if options['create_developers']:
            self._create_developers_for_orphans(orphan_aliases)
    
    def _list_orphan_aliases(self, orphan_aliases):
        """List all orphan aliases with details"""
        self.stdout.write(f'\n📋 Orphan aliases:')
        
        # Group by domain
        domain_stats = defaultdict(list)
        for alias in orphan_aliases:
            domain = alias.email.split('@')[1] if '@' in alias.email else 'unknown'
            domain_stats[domain].append(alias)
        
        for domain, aliases in sorted(domain_stats.items()):
            self.stdout.write(f'\n📧 Domain: {domain} ({len(aliases)} aliases)')
            for alias in aliases:
                self.stdout.write(f'  - {alias.name} ({alias.email}) - {alias.commit_count} commits')
    
    def _reassign_orphan_aliases(self, orphan_aliases):
        """Attempt to reassign orphan aliases to existing developers"""
        self.stdout.write(f'\n🔄 Attempting to reassign orphan aliases...')
        
        reassigned_count = 0
        
        for alias in orphan_aliases:
            # Try to find a developer with the same email domain
            domain = alias.email.split('@')[1] if '@' in alias.email else ''
            
            # Look for developers with similar email domains
            potential_developers = []
            for developer in Developer.objects.all():
                dev_domain = developer.primary_email.split('@')[1] if '@' in developer.primary_email else ''
                
                # Check if domains match or are similar
                if dev_domain == domain:
                    potential_developers.append(developer)
                elif domain in dev_domain or dev_domain in domain:
                    potential_developers.append(developer)
            
            if potential_developers:
                # Choose the developer with the most similar name
                best_match = None
                best_score = 0
                
                for dev in potential_developers:
                    # Simple name similarity check
                    dev_name_words = set(dev.primary_name.lower().split())
                    alias_name_words = set(alias.name.lower().split())
                    
                    common_words = dev_name_words.intersection(alias_name_words)
                    score = len(common_words) / max(len(dev_name_words), len(alias_name_words))
                    
                    if score > best_score and score > 0.1:  # At least 10% similarity
                        best_score = score
                        best_match = dev
                
                if best_match:
                    alias.developer = best_match
                    alias.save()
                    reassigned_count += 1
                    self.stdout.write(f'  ✅ Reassigned {alias.name} ({alias.email}) to {best_match.primary_name}')
        
        self.stdout.write(f'\n📊 Reassignment results:')
        self.stdout.write(f'  - Reassigned: {reassigned_count}')
        self.stdout.write(f'  - Remaining orphans: {orphan_aliases.count() - reassigned_count}')
    
    def _create_developers_for_orphans(self, orphan_aliases):
        """Create new developers for remaining orphan aliases"""
        self.stdout.write(f'\n👤 Creating new developers for orphan aliases...')
        
        created_count = 0
        
        for alias in orphan_aliases:
            if alias.developer is None:  # Still orphan after reassignment
                # Create a new developer
                developer = Developer(
                    primary_name=alias.name,
                    primary_email=alias.email,
                    is_auto_grouped=False,  # Manual creation
                    confidence_score=100  # High confidence since it's manual
                )
                developer.save()
                
                # Associate the alias
                alias.developer = developer
                alias.save()
                
                created_count += 1
                self.stdout.write(f'  ✅ Created developer {developer.primary_name} for {alias.email}')
        
        self.stdout.write(f'\n📊 Developer creation results:')
        self.stdout.write(f'  - New developers created: {created_count}')
        
        # Final check
        remaining_orphans = DeveloperAlias.objects.filter(developer=None).count()
        if remaining_orphans == 0:
            self.stdout.write(self.style.SUCCESS('🎉 All orphan aliases have been handled!'))
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  {remaining_orphans} orphan aliases still remain')
            ) 