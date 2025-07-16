from django.core.management.base import BaseCommand
from analytics.github_service import GitHubService
from github.models import GitHubToken

class Command(BaseCommand):
    help = "Debug GitHub API: affiche la réponse de /commits/:sha/pulls pour un commit donné"

    def add_arguments(self, parser):
        parser.add_argument('repo_full_name', type=str, help='owner/repo')
        parser.add_argument('commit_sha', type=str, help='SHA du commit')

    def handle(self, *args, **options):
        repo_full_name = options['repo_full_name']
        commit_sha = options['commit_sha']

        token_obj = GitHubToken.objects.first()
        if not token_obj:
            self.stderr.write(self.style.ERROR("Aucun token GitHub trouvé en base."))
            return
        service = GitHubService(token_obj.access_token)

        pr_url = f"https://api.github.com/repos/{repo_full_name}/commits/{commit_sha}/pulls"
        try:
            prs, _ = service._make_request(pr_url, params={"per_page": 5})
            self.stdout.write(self.style.SUCCESS(f"Réponse API pour {repo_full_name} {commit_sha} :"))
            self.stdout.write(str(prs))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Erreur lors de l'appel à l'API GitHub : {e}")) 