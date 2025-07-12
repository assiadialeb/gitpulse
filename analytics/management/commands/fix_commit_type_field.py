from django.core.management.base import BaseCommand
from analytics.models import Commit

class Command(BaseCommand):
    help = 'Ajoute le champ commit_type="other" à tous les commits qui ne l\'ont pas.'

    def handle(self, *args, **options):
        missing = Commit.objects(commit_type__exists=False)
        total = missing.count()
        self.stdout.write(f"{total} commits sans commit_type trouvés.")
        updated = 0
        for commit in missing:
            commit.commit_type = 'other'
            commit.save()
            updated += 1
            if updated % 100 == 0:
                self.stdout.write(f"{updated} corrigés...")
        self.stdout.write(self.style.SUCCESS(f"{updated} commits corrigés (champ commit_type ajouté).")) 