"""
Commande Django pour nettoyer et vérifier la configuration OAuth
"""
from django.core.management.base import BaseCommand
from github.models import GitHubApp
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken
from django.contrib.sites.models import Site

class Command(BaseCommand):
    help = 'Clean up and verify OAuth configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix configuration issues automatically'
        )

    def handle(self, *args, **options):
        fix_issues = options['fix']
        
        self.stdout.write("=== Nettoyage Configuration OAuth ===\n")
        
        # 1. Check and sync GitHubApp with SocialApp
        self.stdout.write("1. Synchronisation des configurations:")
        
        site = Site.objects.get_current()
        social_app = SocialApp.objects.filter(provider='github', sites=site).first()
        github_app = GitHubApp.objects.first()
        
        if not social_app:
            self.stdout.write("   ⚠️  Aucune SocialApp GitHub trouvée")
            if fix_issues:
                social_app = SocialApp.objects.create(
                    provider='github',
                    name='GitHub',
                    client_id=github_app.client_id if github_app else '',
                    secret=''
                )
                social_app.sites.add(site)
                self.stdout.write("   ✓ SocialApp créée")
        else:
            self.stdout.write(f"   ✓ SocialApp trouvée: {social_app.client_id}")
        
        if not github_app:
            self.stdout.write("   ⚠️  Aucune GitHubApp trouvée")
            if fix_issues:
                github_app = GitHubApp.objects.create(
                    client_id=social_app.client_id if social_app else '',
                    client_secret=''
                )
                self.stdout.write("   ✓ GitHubApp créée")
        else:
            self.stdout.write(f"   ✓ GitHubApp trouvée: {github_app.client_id}")
        
        # 2. Sync configurations
        if social_app and github_app and fix_issues:
            if social_app.client_id != github_app.client_id:
                github_app.client_id = social_app.client_id
                github_app.save()
                self.stdout.write("   ✓ Client ID synchronisé")
            
            if social_app.secret and social_app.secret != github_app.client_secret:
                github_app.client_secret = social_app.secret
                github_app.save()
                self.stdout.write("   ✓ Client Secret synchronisé")
        
        self.stdout.write("")
        
        # 3. Check for PAT remnants
        self.stdout.write("2. Vérification des résidus PAT:")
        
        pat_found = False
        if github_app and github_app.client_secret:
            if github_app.client_secret.startswith(('ghp_', 'gho_', 'github_pat_')):
                self.stdout.write("   ⚠️  PAT trouvé dans GitHubApp.client_secret")
                pat_found = True
                if fix_issues:
                    # Don't automatically remove PAT, ask user
                    self.stdout.write("   💡 Utilisez --fix avec confirmation manuelle pour nettoyer")
        
        if not pat_found:
            self.stdout.write("   ✓ Aucun résidu PAT trouvé")
        
        self.stdout.write("")
        
        # 4. Check user connections
        self.stdout.write("3. Connexions utilisateurs:")
        
        github_accounts = SocialAccount.objects.filter(provider='github')
        self.stdout.write(f"   📊 {github_accounts.count()} comptes GitHub connectés")
        
        for account in github_accounts:
            user = account.user
            tokens = SocialToken.objects.filter(account=account)
            token_status = "✓" if tokens.exists() else "⚠️"
            self.stdout.write(f"   {token_status} {user.username}: {tokens.count()} tokens")
            
            if not tokens.exists():
                self.stdout.write(f"     💡 {user.username} doit se reconnecter pour obtenir un token")
        
        self.stdout.write("")
        
        # 5. Configuration summary
        self.stdout.write("4. Résumé de la configuration:")
        
        if social_app and social_app.client_id and social_app.secret:
            self.stdout.write("   ✅ OAuth App correctement configurée")
        else:
            self.stdout.write("   ❌ OAuth App incomplète")
        
        # Check scopes in settings
        from django.conf import settings
        providers = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {})
        github_config = providers.get('github', {})
        scopes = github_config.get('SCOPE', [])
        
        required_scopes = ['user:email', 'repo', 'read:org']
        missing_scopes = [scope for scope in required_scopes if scope not in scopes]
        
        if not missing_scopes:
            self.stdout.write("   ✅ Scopes OAuth correctement configurés")
        else:
            self.stdout.write(f"   ⚠️  Scopes manquants: {', '.join(missing_scopes)}")
        
        self.stdout.write("")
        
        # 6. Next steps
        self.stdout.write("5. Prochaines étapes:")
        
        if not (social_app and social_app.client_id and social_app.secret):
            self.stdout.write("   1. Configurer l'OAuth App dans /github/admin/")
        
        if github_accounts.exists() and not SocialToken.objects.filter(account__in=github_accounts).exists():
            self.stdout.write("   2. Les utilisateurs doivent se reconnecter : /accounts/github/login/")
        
        if missing_scopes:
            self.stdout.write("   3. Vérifier SOCIALACCOUNT_PROVIDERS dans settings.py")
        
        self.stdout.write("   4. Tester avec : python manage.py test_github_tokens")
        
        self.stdout.write("\n=== Nettoyage terminé ===")