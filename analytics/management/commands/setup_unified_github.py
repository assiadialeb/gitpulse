"""
Commande Django pour configurer GitHub en mode unifié (OAuth App pour tout)
"""
from django.core.management.base import BaseCommand
from analytics.github_utils import ensure_github_oauth_scopes, sync_github_app_with_oauth
from allauth.socialaccount.models import SocialApp
from github.models import GitHubApp
from django.contrib.sites.models import Site

class Command(BaseCommand):
    help = 'Setup unified GitHub configuration (OAuth App for both auth and API access)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--client-id',
            type=str,
            help='GitHub OAuth App Client ID'
        )
        parser.add_argument(
            '--client-secret',
            type=str,
            help='GitHub OAuth App Client Secret'
        )

    def handle(self, *args, **options):
        """Setup unified GitHub configuration"""
        self.stdout.write("=== Configuration GitHub Unifiée ===\n")
        
        client_id = options.get('client_id')
        client_secret = options.get('client_secret')
        
        # 1. Configure SocialApp (for allauth)
        self.stdout.write("1. Configuration SocialApp (allauth):")
        
        site = Site.objects.get_current()
        social_app, created = SocialApp.objects.get_or_create(
            provider='github',
            defaults={
                'name': 'GitHub',
                'client_id': client_id or '',
                'secret': client_secret or ''
            }
        )
        
        if not created and (client_id or client_secret):
            if client_id:
                social_app.client_id = client_id
            if client_secret:
                social_app.secret = client_secret
            social_app.save()
        
        # Ensure site association
        if site not in social_app.sites.all():
            social_app.sites.add(site)
        
        self.stdout.write(f"   ✓ SocialApp configurée: {social_app.client_id}")
        self.stdout.write(f"   ✓ Secret: {'***' + social_app.secret[-4:] if social_app.secret else 'MANQUANT'}")
        
        # 2. Sync with GitHubApp model
        self.stdout.write("\n2. Synchronisation GitHubApp:")
        
        github_app, created = GitHubApp.objects.get_or_create(
            client_id=social_app.client_id,
            defaults={'client_secret': social_app.secret or ''}
        )
        
        if not created:
            github_app.client_secret = social_app.secret or ''
            github_app.save()
        
        self.stdout.write(f"   ✓ GitHubApp synchronisée: {github_app.client_id}")
        
        # 3. Check configuration
        self.stdout.write("\n3. Vérification de la configuration:")
        
        if not social_app.client_id:
            self.stdout.write("   ⚠️  Client ID manquant")
            self.stdout.write("   💡 Utilisez: --client-id YOUR_CLIENT_ID")
        else:
            self.stdout.write("   ✓ Client ID configuré")
        
        if not social_app.secret:
            self.stdout.write("   ⚠️  Client Secret manquant")
            self.stdout.write("   💡 Utilisez: --client-secret YOUR_CLIENT_SECRET")
        else:
            self.stdout.write("   ✓ Client Secret configuré")
        
        # 4. Show OAuth URLs
        self.stdout.write("\n4. URLs OAuth:")
        callback_url = f"http://{site.domain}/accounts/github/login/callback/"
        self.stdout.write(f"   📋 Callback URL: {callback_url}")
        self.stdout.write("   💡 Ajoutez cette URL dans votre OAuth App GitHub")
        
        # 5. Show required scopes
        self.stdout.write("\n5. Scopes requis:")
        self.stdout.write("   📋 Scopes configurés dans settings.py:")
        self.stdout.write("     • user:email - Accès aux emails")
        self.stdout.write("     • repo - Accès aux repositories")
        self.stdout.write("     • read:org - Lecture des organisations")
        
        # 6. Test instructions
        self.stdout.write("\n6. Test de la configuration:")
        self.stdout.write("   1. Allez sur /accounts/github/login/ pour tester l'auth")
        self.stdout.write("   2. Utilisez 'python manage.py test_github_tokens' pour tester l'API")
        
        # 7. Show advantages
        self.stdout.write("\n7. Avantages de cette configuration:")
        self.stdout.write("   ✅ Une seule configuration OAuth App")
        self.stdout.write("   ✅ Authentification utilisateur + accès API")
        self.stdout.write("   ✅ Chaque utilisateur autorise ses propres repos")
        self.stdout.write("   ✅ Pas de dépendance à un seul PAT")
        self.stdout.write("   ✅ Permissions granulaires par utilisateur")
        
        self.stdout.write("\n=== Configuration terminée ===")
        
        if not (social_app.client_id and social_app.secret):
            self.stdout.write("\n⚠️  N'oubliez pas de fournir client_id et client_secret !")
            self.stdout.write("Exemple: python manage.py setup_unified_github --client-id YOUR_ID --client-secret YOUR_SECRET")