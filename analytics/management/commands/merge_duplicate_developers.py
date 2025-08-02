from django.core.management.base import BaseCommand
from analytics.models import Developer, DeveloperAlias
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Merge duplicate developers based on similar emails'

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
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        else:
            self.stdout.write(self.style.SUCCESS('APPLY MODE - Changes will be made'))
        
        self.stdout.write('\n=== ANALYZING DUPLICATE DEVELOPERS ===')
        
        # Trouver les developers avec des emails similaires
        developers = list(Developer.objects.all())
        duplicates = defaultdict(list)
        
        for dev in developers:
            normalized_email = dev.primary_email.lower()
            duplicates[normalized_email].append(dev)
        
        # Afficher les duplicates trouvés
        merged_count = 0
        for normalized_email, dev_list in duplicates.items():
            if len(dev_list) > 1:
                self.stdout.write(f'\n--- Duplicates for {normalized_email} ---')
                for dev in dev_list:
                    self.stdout.write(f'  {dev.primary_name} | {dev.primary_email}')
                
                if not dry_run:
                    # Garder le premier developer, merger les autres
                    primary_dev = dev_list[0]
                    for dev_to_merge in dev_list[1:]:
                        # Déplacer tous les aliases vers le developer principal
                        aliases_to_move = DeveloperAlias.objects(developer=dev_to_merge)
                        for alias in aliases_to_move:
                            alias.developer = primary_dev
                            alias.save()
                        
                        # Supprimer le developer duplicate
                        dev_to_merge.delete()
                        merged_count += 1
                        self.stdout.write(f'  ✓ Merged {dev_to_merge.primary_email} into {primary_dev.primary_email}')
        
        if merged_count > 0:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Merged {merged_count} duplicate developers'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ No duplicates found'))
        
        # Afficher les statistiques finales
        total_devs = Developer.objects.count()
        total_aliases = DeveloperAlias.objects.count()
        linked_aliases = DeveloperAlias.objects(developer__ne=None).count()
        
        self.stdout.write(f'\n=== FINAL STATISTICS ===')
        self.stdout.write(f'Total Developers: {total_devs}')
        self.stdout.write(f'Total Aliases: {total_aliases}')
        self.stdout.write(f'Linked Aliases: {linked_aliases}')
        self.stdout.write(f'Unlinked Aliases: {total_aliases - linked_aliases}') 