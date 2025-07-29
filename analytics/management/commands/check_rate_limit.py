"""
Management command to check GitHub API rate limit status
"""
from django.core.management.base import BaseCommand
from analytics.github_token_service import GitHubTokenService
import requests
import datetime
from django.utils import timezone as dt_timezone


class Command(BaseCommand):
    help = 'Check GitHub API rate limit status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to check rate limit for (default: all users)',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        
        if user_id:
            self.check_user_rate_limit(user_id)
        else:
            self.check_all_rate_limits()

    def check_user_rate_limit(self, user_id):
        """Check rate limit for a specific user"""
        self.stdout.write(f"\nChecking rate limit for user {user_id}:")
        
        # Get user token
        user_token = GitHubTokenService._get_user_token(user_id)
        if not user_token:
            self.stdout.write(self.style.WARNING(f"No token found for user {user_id}"))
            return
        
        self.check_token_rate_limit(user_token, f"User {user_id}")

    def check_all_rate_limits(self):
        """Check rate limits for all available tokens"""
        from allauth.socialaccount.models import SocialToken
        
        self.stdout.write("Checking GitHub API rate limits...\n")
        
        # Check OAuth App token
        oauth_token = GitHubTokenService._get_oauth_app_token()
        if oauth_token:
            self.check_token_rate_limit(oauth_token, "OAuth App")
        
        # Check user tokens
        user_tokens = SocialToken.objects.filter(app__provider='github')
        for token in user_tokens:
            user = token.account.user
            self.check_token_rate_limit(token.token, f"User {user.username} ({user.id})")

    def check_token_rate_limit(self, token, token_name):
        """Check rate limit for a specific token"""
        headers = {'Authorization': f'token {token}'}
        
        try:
            response = requests.get('https://api.github.com/rate_limit', headers=headers)
            if response.status_code == 200:
                rate_limit = response.json()
                core = rate_limit['resources']['core']
                
                self.stdout.write(f"{token_name}:")
                self.stdout.write(f"  Limit: {core['limit']}")
                self.stdout.write(f"  Used: {core['used']}")
                self.stdout.write(f"  Remaining: {core['remaining']}")
                
                reset_time = datetime.datetime.fromtimestamp(core['reset'])
                self.stdout.write(f"  Reset at: {reset_time}")
                
                # Time until reset
                now = datetime.now(dt_timezone.utc)
                time_until_reset = reset_time - now
                if time_until_reset.total_seconds() > 0:
                    self.stdout.write(f"  Time until reset: {time_until_reset}")
                else:
                    self.stdout.write(self.style.SUCCESS("  Rate limit has been reset!"))
                
                # Status
                if core['remaining'] == 0:
                    self.stdout.write(self.style.ERROR("  STATUS: RATE LIMITED"))
                elif core['remaining'] < 100:
                    self.stdout.write(self.style.WARNING("  STATUS: LOW REMAINING"))
                else:
                    self.stdout.write(self.style.SUCCESS("  STATUS: OK"))
                    
            else:
                self.stdout.write(self.style.ERROR(f"{token_name}: Error {response.status_code}"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"{token_name}: Error - {e}"))
        
        self.stdout.write("")  # Empty line