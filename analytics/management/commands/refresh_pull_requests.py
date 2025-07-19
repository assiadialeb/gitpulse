from django.core.management.base import BaseCommand
from analytics.models import PullRequest
from analytics.tasks import fetch_all_pull_requests_detailed_task
from django_q.tasks import async_task
from applications.models import Application
from analytics.github_service import GitHubService
from analytics.github_token_service import GitHubTokenService
import dateutil.parser
import time
import logging

logger = logging.getLogger(__name__)


def fetch_prs_for_app(app_id, max_pages_per_repo=50):
    """Fonction simplifiée pour récupérer les PRs d'une app spécifique"""
    try:
        app = Application.objects.get(id=app_id)
        user_id = app.owner_id
        access_token = GitHubTokenService.get_token_for_operation('private_repos', user_id)
        
        if not access_token:
            print(f"❌ Pas de token GitHub trouvé pour l'utilisateur {user_id}")
            return False
            
        gh = GitHubService(access_token)
        total_saved = 0
        
        for repo in app.repositories.all():
            repo_name = repo.github_repo_name
            print(f"📦 Traitement du repo: {repo_name}")
            
            page = 1
            while page <= max_pages_per_repo:
                url = f"https://api.github.com/repos/{repo_name}/pulls"
                params = {'state': 'closed', 'per_page': 100, 'page': page}
                
                try:
                    prs, _ = gh._make_request(url, params)
                    
                    if not prs or len(prs) == 0:
                        print(f"   ✅ Plus de PRs, arrêt à la page {page}")
                        break
                        
                    print(f"   📄 Page {page}: {len(prs)} PRs récupérées")
                    
                    for pr in prs:
                        pr_number = pr.get('number')
                        
                        # Récupérer les détails complets de la PR
                        detailed_url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
                        detailed_pr, _ = gh._make_request(detailed_url)
                        
                        if detailed_pr:
                            pr = detailed_pr
                        
                        obj = PullRequest.objects(
                            application_id=app.id, 
                            repository_full_name=repo_name, 
                            number=pr_number
                        ).first()
                        
                        if not obj:
                            obj = PullRequest(
                                application_id=app.id,
                                repository_full_name=repo_name,
                                number=pr_number
                            )
                            
                        obj.title = pr.get('title')
                        obj.author = pr.get('user', {}).get('login')
                        obj.created_at = dateutil.parser.parse(pr.get('created_at')) if pr.get('created_at') else None
                        obj.updated_at = dateutil.parser.parse(pr.get('updated_at')) if pr.get('updated_at') else None
                        obj.closed_at = dateutil.parser.parse(pr.get('closed_at')) if pr.get('closed_at') else None
                        obj.merged_at = dateutil.parser.parse(pr.get('merged_at')) if pr.get('merged_at') else None
                        obj.state = pr.get('state')
                        obj.url = pr.get('html_url')
                        obj.labels = [l['name'] for l in pr.get('labels', [])]
                        
                        # Nouveaux champs pour les métriques détaillées
                        obj.merged_by = pr.get('merged_by', {}).get('login') if pr.get('merged_by') else None
                        obj.requested_reviewers = [r.get('login') for r in pr.get('requested_reviewers', [])]
                        obj.assignees = [a.get('login') for a in pr.get('assignees', [])]
                        obj.review_comments_count = pr.get('review_comments', 0)
                        obj.comments_count = pr.get('comments', 0)
                        obj.commits_count = pr.get('commits', 0)
                        obj.additions_count = pr.get('additions', 0)
                        obj.deletions_count = pr.get('deletions', 0)
                        obj.changed_files_count = pr.get('changed_files', 0)
                        
                        obj.payload = pr
                        obj.save()
                        
                        total_saved += 1
                        
                        # Petit délai pour éviter de surcharger l'API
                        time.sleep(0.1)
                        
                    page += 1
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"   ❌ Erreur page {page}: {e}")
                    break
                    
        print(f"✅ Total: {total_saved} PRs sauvegardées pour l'app {app_id}")
        return True
        
    except Exception as e:
        print(f"❌ Erreur générale: {e}")
        return False


class Command(BaseCommand):
    help = 'Vide et réindexe toutes les Pull Requests avec des données détaillées'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app-id',
            type=int,
            help='ID de l\'application spécifique à traiter (optionnel)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche ce qui serait fait sans exécuter'
        )
        parser.add_argument(
            '--max-repos',
            type=int,
            default=10,
            help='Nombre maximum de repos à traiter par exécution (défaut: 10)'
        )

    def handle(self, *args, **options):
        app_id = options.get('app_id')
        dry_run = options.get('dry_run')
        max_repos = options.get('max_repos')

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Ceci affiche ce qui serait fait sans exécuter'
                )
            )

        # Compter les PRs existantes
        if app_id:
            existing_count = PullRequest.objects(application_id=app_id).count()
            self.stdout.write(
                f'PRs existantes pour l\'app {app_id}: {existing_count}'
            )
        else:
            existing_count = PullRequest.objects.count()
            self.stdout.write(f'PRs existantes totales: {existing_count}')

        if not dry_run:
            # Supprimer les PRs existantes
            if app_id:
                deleted_count = PullRequest.objects(application_id=app_id).delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Supprimé {deleted_count} PRs pour l\'app {app_id}'
                    )
                )
                
                # Utiliser la fonction simplifiée pour l'app spécifique
                success = fetch_prs_for_app(app_id)
                if success:
                    self.stdout.write(
                        self.style.SUCCESS(
                            '✅ Réindexation des PRs terminée avec succès!'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            '❌ Erreur lors de la réindexation'
                        )
                    )
            else:
                deleted_count = PullRequest.objects.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'Supprimé {deleted_count} PRs totales')
                )

                # Lancer la tâche asynchrone
                task_id = async_task(
                    fetch_all_pull_requests_detailed_task,
                    max_pages_per_repo=50,
                    max_repos_per_run=max_repos
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Tâche de réindexation lancée avec ID: {task_id}'
                    )
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        '✅ Réindexation des PRs lancée avec succès!'
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    'DRY RUN: Les PRs auraient été supprimées et réindexées'
                )
            ) 