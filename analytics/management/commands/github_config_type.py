"""
Commande Django pour diagnostiquer le type de configuration GitHub
"""
from django.core.management.base import BaseCommand
from github.models import GitHubApp, GitHubInstallation
from allauth.socialaccount.models import SocialApp, SocialToken
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Diagnose GitHub configuration type and recommend best approach'

    def handle(self, *args, **options):
        """Diagnose GitHub configuration"""
        self.stdout.write("=== Diagnostic de la configuration GitHub ===\n")
        
        # 1. Check GitHubApp configuration
        self.stdout.write("1. Configuration GitHubApp (modèle custom):")
        github_app = GitHubApp.objects.first()
        if github_app:
            self.stdout.write(f"   ✓ Client ID: {github_app.client_id}")
            
            # Detect type based on client_secret
            if github_app.client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
                self.stdout.write("   📝 Type détecté: Personal Access Token (PAT)")
                self.stdout.write("   ⚠️  Limitation: Accès limité aux repos de l'utilisateur du PAT")
            elif github_app.client_secret.startswith('-----BEGIN'):
                self.stdout.write("   📝 Type détecté: GitHub App (clé privée)")
                self.stdout.write("   ✅ Recommandé pour les organisations")
            else:
                self.stdout.write("   📝 Type détecté: OAuth App (client secret)")
                self.stdout.write("   ⚠️  Nécessite le flux OAuth pour chaque utilisateur")
        else:
            self.stdout.write("   ✗ Aucune configuration GitHubApp")
        
        self.stdout.write("")
        
        # 2. Check SocialApp (django-allauth)
        self.stdout.write("2. Configuration SocialApp (django-allauth):")
        social_app = SocialApp.objects.filter(provider='github').first()
        if social_app:
            self.stdout.write(f"   ✓ Client ID: {social_app.client_id}")
            self.stdout.write(f"   ✓ Secret configuré: {'Oui' if social_app.secret else 'Non'}")
            
            # Count user tokens
            user_tokens = SocialToken.objects.filter(app=social_app).count()
            self.stdout.write(f"   📊 Tokens utilisateurs: {user_tokens}")
        else:
            self.stdout.write("   ✗ Aucune configuration SocialApp")
        
        self.stdout.write("")
        
        # 3. Check GitHub App installations
        self.stdout.write("3. Installations GitHub App:")
        installations = GitHubInstallation.objects.all()
        if installations.exists():
            for installation in installations:
                self.stdout.write(f"   ✓ {installation.account_login} ({installation.account_type})")
                self.stdout.write(f"     Installation ID: {installation.installation_id}")
        else:
            self.stdout.write("   - Aucune installation GitHub App")
        
        self.stdout.write("")
        
        # 4. Recommendations
        self.stdout.write("4. Recommandations:")
        
        if github_app and github_app.client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
            self.stdout.write("   📋 Configuration actuelle: PAT")
            self.stdout.write("   ✅ Avantages:")
            self.stdout.write("     • Simple à configurer")
            self.stdout.write("     • Fonctionne immédiatement")
            self.stdout.write("   ⚠️  Inconvénients:")
            self.stdout.write("     • Limité aux repos accessibles par le propriétaire du PAT")
            self.stdout.write("     • Pas de gestion granulaire des permissions")
            self.stdout.write("     • Dépend d'un seul utilisateur")
            
            self.stdout.write("\n   🚀 Pour une organisation, considérez:")
            self.stdout.write("     1. GitHub App - Accès au niveau organisation")
            self.stdout.write("     2. OAuth App + flux utilisateur - Permissions par utilisateur")
            
        elif installations.exists():
            self.stdout.write("   📋 Configuration actuelle: GitHub App")
            self.stdout.write("   ✅ Excellente configuration pour les organisations!")
            self.stdout.write("   ✅ Avantages:")
            self.stdout.write("     • Accès au niveau organisation")
            self.stdout.write("     • Permissions granulaires")
            self.stdout.write("     • Gestion centralisée")
            
        else:
            self.stdout.write("   📋 Configuration actuelle: OAuth App")
            self.stdout.write("   ⚠️  Nécessite l'implémentation du flux OAuth")
            self.stdout.write("   💡 Solutions:")
            self.stdout.write("     1. Implémenter le flux OAuth complet")
            self.stdout.write("     2. Migrer vers GitHub App")
            self.stdout.write("     3. Utiliser un PAT temporairement")
        
        self.stdout.write("\n=== Diagnostic terminé ===")