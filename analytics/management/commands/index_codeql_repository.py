"""
Management command to index CodeQL vulnerabilities for a specific repository
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from repositories.models import Repository
from analytics.codeql_indexing_service import get_codeql_indexing_service_for_user
from analytics.tasks import index_codeql_intelligent_task
from django_q.tasks import async_task
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command for indexing CodeQL vulnerabilities for a specific repository"""
    
    help = 'Index CodeQL security vulnerabilities for a specific repository'

    def add_arguments(self, parser):
        parser.add_argument(
            'repository_id',
            type=int,
            help='Repository ID to index CodeQL vulnerabilities for'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to use for GitHub token access (defaults to repository owner)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reindexing even if recently analyzed'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Run indexing asynchronously using Django-Q'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed indexing information'
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Use a specific GitHub token instead of user token'
        )

    def handle(self, *args, **options):
        """Execute the command"""
        repository_id = options['repository_id']
        user_id = options.get('user_id')
        force = options['force']
        async_mode = options['async']
        verbose = options['verbose']
        custom_token = options.get('token')
        
        # Set up console logging for this command
        console_handler = logging.StreamHandler(self.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting CodeQL indexing for repository ID: {repository_id}')
        )
        
        try:
            # Find repository
            repository = self._find_repository(repository_id)
            
            # Determine user ID
            if user_id is None:
                user_id = repository.owner.id
                self.stdout.write(f'Using repository owner user ID: {user_id}')
            else:
                self.stdout.write(f'Using specified user ID: {user_id}')
            
            # Check if user has GitHub token
            from analytics.github_token_service import GitHubTokenService
            
            if custom_token:
                user_token = custom_token
                self.stdout.write('✅ Using custom GitHub token')
            else:
                user_token = GitHubTokenService._get_user_token(user_id)
                if not user_token:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ User {user_id} has no GitHub token configured.')
                    )
                    self.stdout.write('CodeQL indexing requires a GitHub token with repository access.')
                    self.stdout.write('Please configure a GitHub token for this user.')
                    self.stdout.write('Or use --token option to provide a custom token.')
                    return
                else:
                    self.stdout.write(f'✅ Found GitHub token for user {user_id}')
                
                # Test token permissions
                import requests
                headers = {'Authorization': f'token {user_token}'}
                try:
                    # Test basic access
                    test_response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
                    
                    # Check rate limit info from the first request
                    rate_limit_remaining = int(test_response.headers.get('X-RateLimit-Remaining', 0))
                    rate_limit_limit = int(test_response.headers.get('X-RateLimit-Limit', 0))
                    rate_limit_reset = int(test_response.headers.get('X-RateLimit-Reset', 0))
                    
                    self.stdout.write(f'Rate limit: {rate_limit_remaining}/{rate_limit_limit} remaining')
                    
                    if test_response.status_code == 200:
                        self.stdout.write('✅ GitHub token is valid')
                        
                        # Test repository access
                        repo_response = requests.get(f'https://api.github.com/repos/{repository.full_name}', headers=headers, timeout=10)
                        if repo_response.status_code == 200:
                            self.stdout.write('✅ Repository access confirmed')
                        else:
                            self.stdout.write(
                                self.style.WARNING(f'⚠️ Repository access denied (status: {repo_response.status_code})')
                            )
                        
                        # Test CodeQL access specifically
                        codeql_response = requests.get(f'https://api.github.com/repos/{repository.full_name}/code-scanning/alerts', headers=headers, timeout=10)
                        
                        if codeql_response.status_code == 200:
                            self.stdout.write('✅ CodeQL access confirmed')
                        elif codeql_response.status_code == 403:
                            if rate_limit_remaining == 0:
                                reset_time = datetime.fromtimestamp(rate_limit_reset)
                                self.stdout.write(
                                    self.style.ERROR(f'❌ Rate limit exceeded (status: {codeql_response.status_code})')
                                )
                                self.stdout.write(f'Rate limit resets at: {reset_time}')
                                self.stdout.write('Please wait or use a different token with higher limits')
                                return
                            else:
                                self.stdout.write(
                                    self.style.ERROR(f'❌ CodeQL access denied (status: {codeql_response.status_code})')
                                )
                                self.stdout.write('The token does not have security_events permission required for CodeQL')
                                return
                        elif codeql_response.status_code == 404:
                            self.stdout.write('⚠️ CodeQL not enabled on this repository')
                        else:
                            self.stdout.write(f'⚠️ CodeQL access test returned status: {codeql_response.status_code}')
                            
                    elif test_response.status_code == 403:
                        if rate_limit_remaining == 0:
                            reset_time = datetime.fromtimestamp(rate_limit_reset)
                            self.stdout.write(
                                self.style.ERROR(f'❌ Rate limit exceeded (status: {test_response.status_code})')
                            )
                            self.stdout.write(f'Rate limit resets at: {reset_time}')
                            self.stdout.write('Please wait or use a different token with higher limits')
                            return
                        else:
                            self.stdout.write(
                                self.style.ERROR(f'❌ GitHub token is invalid (status: {test_response.status_code})')
                            )
                            return
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'❌ GitHub token is invalid (status: {test_response.status_code})')
                        )
                        return
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Could not verify GitHub token: {e}')
                    )
                    return
            
            if async_mode:
                self._run_async_indexing(repository, user_id, force)
            else:
                self._run_sync_indexing(repository, user_id, force, verbose)
            
        except Exception as e:
            raise CommandError(f'CodeQL indexing failed: {e}')

    def _find_repository(self, repository_id):
        """Find repository by ID"""
        try:
            repository = Repository.objects.get(id=repository_id)
            self.stdout.write(f'Found repository: {repository.full_name} (ID: {repository.id})')
            return repository
        except Repository.DoesNotExist:
            raise CommandError(
                f'Repository with ID "{repository_id}" not found. '
                f'Make sure the repository exists and is indexed.'
            )

    def _run_async_indexing(self, repository, user_id, force):
        """Run CodeQL indexing asynchronously using Django-Q"""
        self.stdout.write('Scheduling async CodeQL indexing task...')
        
        try:
            # Schedule the task
            task_id = async_task(
                'analytics.tasks.index_codeql_intelligent_task',
                repository.id,
                group=f'codeql_indexing_{repository.id}',
                timeout=1800  # 30 minute timeout
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'CodeQL indexing task scheduled successfully!')
            )
            self.stdout.write(f'Task ID: {task_id}')
            self.stdout.write(f'Repository: {repository.full_name}')
            self.stdout.write(f'User ID: {user_id}')
            self.stdout.write(f'Force reindex: {"Yes" if force else "No"}')
            self.stdout.write('')
            self.stdout.write('You can monitor the task progress in the Django admin or logs.')
            
        except Exception as e:
            raise CommandError(f'Failed to schedule async task: {e}')

    def _run_sync_indexing(self, repository, user_id, force, verbose):
        """Run CodeQL indexing synchronously"""
        self.stdout.write('Running CodeQL indexing synchronously...')
        
        try:
            # Get CodeQL indexing service
            indexing_service = get_codeql_indexing_service_for_user(user_id)
            
            # Run indexing
            start_time = timezone.now()
            results = indexing_service.index_codeql_for_repository(
                repository_id=repository.id,
                repository_full_name=repository.full_name,
                force_reindex=force
            )
            end_time = timezone.now()
            
            # Display results
            self._display_results(results, start_time, end_time, verbose)
            
        except Exception as e:
            raise CommandError(f'CodeQL indexing failed: {e}')

    def _display_results(self, results, start_time, end_time, verbose):
        """Display indexing results"""
        duration = end_time - start_time
        
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write('CODEQL INDEXING RESULTS')
        self.stdout.write('=' * 60)
        
        status = results.get('status', 'unknown')
        if status == 'success':
            self.stdout.write(self.style.SUCCESS(f'Status: {status.upper()}'))
        elif status == 'not_available':
            self.stdout.write(self.style.WARNING(f'Status: {status.upper()}'))
        elif status == 'permission_denied':
            self.stdout.write(self.style.ERROR(f'Status: {status.upper()}'))
        elif status == 'error':
            self.stdout.write(self.style.ERROR(f'Status: {status.upper()}'))
        else:
            self.stdout.write(self.style.WARNING(f'Status: {status.upper()}'))
        
        # Show metrics
        self.stdout.write(f'Repository: {results.get("repository_full_name", "N/A")}')
        self.stdout.write(f'Repository ID: {results.get("repository_id", "N/A")}')
        self.stdout.write(f'Vulnerabilities processed: {results.get("vulnerabilities_processed", 0)}')
        self.stdout.write(f'New vulnerabilities: {results.get("vulnerabilities_new", 0)}')
        self.stdout.write(f'Updated vulnerabilities: {results.get("vulnerabilities_updated", 0)}')
        self.stdout.write(f'Removed vulnerabilities: {results.get("vulnerabilities_removed", 0)}')
        self.stdout.write(f'Duration: {duration.total_seconds():.2f} seconds')
        
        # Show reason if not available
        if status == 'not_available':
            reason = results.get('reason', 'Unknown reason')
            self.stdout.write(f'Reason: {reason}')
        
        # Show errors if any
        errors = results.get('errors', [])
        if errors:
            self.stdout.write(self.style.ERROR('\nErrors encountered:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        # Show timing info
        started_at = results.get('started_at')
        completed_at = results.get('completed_at')
        if started_at and completed_at:
            self.stdout.write(f'Started: {started_at}')
            self.stdout.write(f'Completed: {completed_at}')
        
        # Show summary
        if status == 'success':
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ CodeQL indexing completed successfully!'))
            if results.get('vulnerabilities_new', 0) > 0:
                self.stdout.write(f'📊 Found {results.get("vulnerabilities_new")} new vulnerabilities')
            if results.get('vulnerabilities_updated', 0) > 0:
                self.stdout.write(f'🔄 Updated {results.get("vulnerabilities_updated")} existing vulnerabilities')
        elif status == 'not_available':
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('⚠️ CodeQL analysis not available for this repository'))
            self.stdout.write('This usually means CodeQL is not enabled on the repository.')
        elif status == 'permission_denied':
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('❌ GitHub token permission denied'))
            self.stdout.write('The GitHub token does not have required permissions for CodeQL access.')
            self.stdout.write('Required permissions: repo, security_events')
            self.stdout.write('Please update the token permissions or use a different token.')
        elif status == 'error':
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('❌ CodeQL indexing failed'))
            self.stdout.write('Check the error messages above for details.')

    def _show_help_text(self):
        """Show additional help information"""
        self.stdout.write('')
        self.stdout.write('Additional Information:')
        self.stdout.write('- Use --async to run indexing in background')
        self.stdout.write('- Use --force to reindex even if recently analyzed')
        self.stdout.write('- Use --verbose for detailed output')
        self.stdout.write('- Repository must be indexed first before CodeQL analysis')
        self.stdout.write('- GitHub token with code scanning permissions required') 