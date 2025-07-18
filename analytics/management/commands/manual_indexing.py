"""
Commande Django pour lancer une indexation manuelle
"""
from django.core.management.base import BaseCommand
from applications.models import Application
from analytics.tasks import manual_indexing_task
from django_q.tasks import async_task
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Launch manual indexing for an application'

    def add_arguments(self, parser):
        parser.add_argument(
            'application_id',
            type=int,
            help='ID of the application to index'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously instead of as background task'
        )

    def handle(self, *args, **options):
        application_id = options['application_id']
        sync = options['sync']
        
        try:
            application = Application.objects.get(id=application_id)
            self.stdout.write(f"Application trouvée: {application.name} (Owner: {application.owner.username})")
            
            if sync:
                # Run synchronously
                self.stdout.write("Lancement de l'indexation synchrone...")
                result = manual_indexing_task(application_id, application.owner_id)
                self.stdout.write(f"Indexation terminée: {result}")
            else:
                # Run as background task
                task_id = async_task(
                    'analytics.tasks.manual_indexing_task',
                    application_id,
                    application.owner_id,
                    group=f'manual_indexing_cmd_{application_id}',
                    timeout=7200  # 2 hour timeout
                )
                self.stdout.write(f"Tâche d'indexation lancée: {task_id}")
                self.stdout.write("Utilisez 'python manage.py qmonitor' pour suivre le progrès")
            
        except Application.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Application {application_id} non trouvée"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur: {e}"))