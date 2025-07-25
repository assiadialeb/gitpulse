"""
Commande Django pour vérifier les permissions du token GitHub
"""
from django.core.management.base import BaseCommand
from analytics.github_utils import get_github_token_for_user
from analytics.github_service import GitHubService

import requests

class Command(BaseCommand):
    help = 'Check GitHub token permissions and repository access'

    def handle(self, *args, **options):
        """Check GitHub token permissions"""
        self.stdout.write("=== Vérification des permissions GitHub ===\n")
        
        # Get first application to test
        app = Application.objects.first()
        if not app:
            self.stdout.write("Aucune application trouvée pour tester")
            return
        
        token = get_github_token_for_user(app.owner_id)
        if not token:
            self.stdout.write("Aucun token GitHub trouvé")
            return
        
        # 1. Check token info
        self.stdout.write("1. Informations du token:")
        try:
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get user info
            response = requests.get('https://api.github.com/user', headers=headers)
            if response.status_code == 200:
                user_info = response.json()
                self.stdout.write(f"   ✓ Utilisateur: {user_info.get('login')}")
                self.stdout.write(f"   ✓ Type: {user_info.get('type')}")
            else:
                self.stdout.write(f"   ✗ Erreur récupération utilisateur: {response.status_code}")
                return
            
            # Check token scopes
            scopes = response.headers.get('X-OAuth-Scopes', '')
            self.stdout.write(f"   ✓ Scopes: {scopes if scopes else 'Aucun scope détecté'}")
            
        except Exception as e:
            self.stdout.write(f"   ✗ Erreur: {e}")
            return
        
        self.stdout.write("")
        
        # 2. Test repository access
        self.stdout.write("2. Test d'accès aux repositories:")
        
        repos_tested = 0
        repos_accessible = 0
        repos_not_accessible = 0
        
        for app in Application.objects.all()[:5]:  # Test 5 apps max
            for repo in app.repositories.all()[:3]:  # Test 3 repos par app max
                if repos_tested >= 10:  # Limite globale
                    break
                    
                repo_name = repo.github_repo_name
                repos_tested += 1
                
                try:
                    url = f"https://api.github.com/repos/{repo_name}"
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        repo_info = response.json()
                        repos_accessible += 1
                        privacy = "Privé" if repo_info.get('private') else "Public"
                        self.stdout.write(f"   ✓ {repo_name} - {privacy}")
                    elif response.status_code == 404:
                        repos_not_accessible += 1
                        self.stdout.write(f"   ✗ {repo_name} - Repository not found (404)")
                    elif response.status_code == 403:
                        repos_not_accessible += 1
                        self.stdout.write(f"   ✗ {repo_name} - Access forbidden (403)")
                    else:
                        repos_not_accessible += 1
                        self.stdout.write(f"   ✗ {repo_name} - Erreur {response.status_code}")
                        
                except Exception as e:
                    repos_not_accessible += 1
                    self.stdout.write(f"   ✗ {repo_name} - Erreur: {e}")
            
            if repos_tested >= 10:
                break
        
        self.stdout.write("")
        
        # 3. Summary and recommendations
        self.stdout.write("3. Résumé:")
        self.stdout.write(f"   • Repositories testés: {repos_tested}")
        self.stdout.write(f"   • Accessibles: {repos_accessible}")
        self.stdout.write(f"   • Non accessibles: {repos_not_accessible}")
        
        if repos_not_accessible > 0:
            self.stdout.write("\n4. Recommandations:")
            self.stdout.write("   Les repositories non accessibles peuvent être dus à:")
            self.stdout.write("   • Le token n'a pas les permissions 'repo' pour les repos privés")
            self.stdout.write("   • Le token n'a pas accès à l'organisation")
            self.stdout.write("   • Les repositories ont été supprimés ou renommés")
            self.stdout.write("")
            self.stdout.write("   Solutions:")
            self.stdout.write("   1. Vérifiez que votre PAT a les scopes 'repo' et 'read:org'")
            self.stdout.write("   2. Si c'est une organisation, assurez-vous d'avoir autorisé le PAT")
            self.stdout.write("   3. Mettez à jour la liste des repositories dans vos applications")
        else:
            self.stdout.write("\n   ✓ Tous les repositories sont accessibles !")
        
        self.stdout.write("\n=== Vérification terminée ===")