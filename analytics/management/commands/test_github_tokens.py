"""
Commande Django pour tester le nouveau service de tokens GitHub
"""
from django.core.management.base import BaseCommand
from analytics.github_token_service import GitHubTokenService
from applications.models import Application
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Test the new GitHub token service and diagnose token issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Test with specific user ID'
        )
        parser.add_argument(
            '--operation',
            type=str,
            choices=['basic', 'public_repos', 'private_repos', 'user_info', 'org_access', 'full_access'],
            default='private_repos',
            help='Test specific operation type'
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate token access and scopes'
        )

    def handle(self, *args, **options):
        """Test GitHub token service"""
        self.stdout.write("=== Test du Service de Tokens GitHub ===\n")
        
        user_id = options.get('user_id')
        operation = options.get('operation')
        validate = options.get('validate')
        
        # Test 1: Basic operations (OAuth App token)
        self.stdout.write("1. Test des opérations basiques (OAuth App token):")
        basic_token = GitHubTokenService.get_token_for_operation('basic')
        if basic_token:
            self.stdout.write(f"   ✓ Token OAuth App trouvé: {basic_token[:20]}...")
            if validate:
                validation = GitHubTokenService.validate_token_access(basic_token)
                if validation['valid']:
                    self.stdout.write(f"   ✓ Token valide - Scopes: {validation['scopes']}")
                    self.stdout.write(f"   ✓ Rate limit: {validation['rate_limit']['remaining']}/{validation['rate_limit']['limit']}")
                else:
                    self.stdout.write(f"   ✗ Token invalide: {validation['error']}")
        else:
            self.stdout.write("   ✗ Aucun token OAuth App trouvé")
        
        self.stdout.write("")
        
        # Test 2: User-specific operations
        if user_id:
            self.stdout.write(f"2. Test des opérations utilisateur (user_id: {user_id}):")
            user_token = GitHubTokenService.get_token_for_operation(operation, user_id)
            if user_token:
                self.stdout.write(f"   ✓ Token utilisateur trouvé pour {operation}: {user_token[:20]}...")
                if validate:
                    validation = GitHubTokenService.validate_token_access(user_token)
                    if validation['valid']:
                        self.stdout.write(f"   ✓ Token valide - Scopes: {validation['scopes']}")
                        self.stdout.write(f"   ✓ Rate limit: {validation['rate_limit']['remaining']}/{validation['rate_limit']['limit']}")
                        
                        # Check if required scopes are present
                        required_scopes = GitHubTokenService.SCOPES.get(operation, [])
                        missing_scopes = [scope for scope in required_scopes if scope not in validation['scopes']]
                        if missing_scopes:
                            self.stdout.write(f"   ⚠️  Scopes manquants: {missing_scopes}")
                        else:
                            self.stdout.write(f"   ✓ Tous les scopes requis présents")
                    else:
                        self.stdout.write(f"   ✗ Token invalide: {validation['error']}")
            else:
                self.stdout.write(f"   ✗ Aucun token utilisateur trouvé pour {operation}")
        else:
            self.stdout.write("2. Test des opérations utilisateur:")
            # Test with all users
            users = User.objects.all()[:5]  # Test first 5 users
            for user in users:
                user_token = GitHubTokenService.get_token_for_operation(operation, user.id)
                if user_token:
                    self.stdout.write(f"   ✓ User {user.username} (ID: {user.id}): Token trouvé")
                else:
                    self.stdout.write(f"   ✗ User {user.username} (ID: {user.id}): Pas de token")
        
        self.stdout.write("")
        
        # Test 3: Repository access
        self.stdout.write("3. Test d'accès aux repositories:")
        applications = Application.objects.all()[:3]  # Test first 3 applications
        for app in applications:
            self.stdout.write(f"   Application: {app.name} (ID: {app.id})")
            repos = app.repositories.all()[:2]  # Test first 2 repos per app
            for repo in repos:
                repo_token = GitHubTokenService.get_token_for_repository_access(app.owner_id, repo.github_repo_name)
                if repo_token:
                    self.stdout.write(f"     ✓ {repo.github_repo_name}: Token trouvé")
                else:
                    self.stdout.write(f"     ✗ {repo.github_repo_name}: Pas de token")
        
        self.stdout.write("")
        
        # Test 4: API endpoint access
        self.stdout.write("4. Test d'accès aux endpoints API:")
        test_endpoints = [
            '/user',
            '/user/repos',
            '/repos/owner/repo/commits'
        ]
        
        if user_id:
            for endpoint in test_endpoints:
                token = GitHubTokenService.get_token_for_api_call(user_id, endpoint)
                if token:
                    self.stdout.write(f"   ✓ {endpoint}: Token trouvé")
                else:
                    self.stdout.write(f"   ✗ {endpoint}: Pas de token")
        else:
            self.stdout.write("   (Skipped - requires --user-id)")
        
        self.stdout.write("")
        
        # Test 5: Token validation summary
        if validate:
            self.stdout.write("5. Résumé de validation des tokens:")
            all_tokens = []
            
            # Collect all available tokens
            basic_token = GitHubTokenService.get_token_for_operation('basic')
            if basic_token:
                all_tokens.append(('OAuth App', basic_token))
            
            for user in User.objects.all()[:3]:
                user_token = GitHubTokenService.get_token_for_operation('private_repos', user.id)
                if user_token:
                    all_tokens.append((f'User {user.username}', user_token))
            
            for token_name, token in all_tokens:
                validation = GitHubTokenService.validate_token_access(token)
                if validation['valid']:
                    self.stdout.write(f"   ✓ {token_name}: Valide")
                    self.stdout.write(f"      Scopes: {', '.join(validation['scopes'])}")
                    self.stdout.write(f"      Rate limit: {validation['rate_limit']['remaining']}/{validation['rate_limit']['limit']}")
                else:
                    self.stdout.write(f"   ✗ {token_name}: {validation['error']}")
        
        self.stdout.write("\n=== Test terminé ===") 