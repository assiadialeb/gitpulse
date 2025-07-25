"""
Commande Django pour lancer une indexation manuelle
"""
from django.core.management.base import BaseCommand
from repositories.models import Repository
from analytics.tasks import manual_indexing_task
from django_q.tasks import async_task
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Launch manual indexing for a repository'

    def add_arguments(self, parser):
        parser.add_argument(
            'repository_id',
            type=int,
            help='ID of the repository to index'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously instead of as background task'
        )

    def handle(self, *args, **options):
        repository_id = options['repository_id']
        sync = options['sync']
        
        try:
            repository = Repository.objects.get(id=repository_id)
            self.stdout.write(f"Repository trouvé: {repository.full_name} (Owner: {repository.owner.username})")
            
            if sync:
                # Run synchronously
                self.stdout.write("Lancement de l'indexation synchrone...")
                result = manual_indexing_task(repository_id, repository.owner_id)
                self.stdout.write(f"Indexation terminée: {result}")
            else:
                # Run as background task
                task_id = async_task(
                    'analytics.tasks.manual_indexing_task',
                    repository_id,
                    repository.owner_id,
                    group=f'manual_indexing_cmd_{repository_id}',
                    timeout=7200  # 2 hour timeout
                )
                self.stdout.write(f"Tâche d'indexation lancée: {task_id}")
                self.stdout.write("Utilisez 'python manage.py qmonitor' pour suivre le progrès")
            
        except Repository.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Repository {repository_id} non trouvé"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur: {e}"))