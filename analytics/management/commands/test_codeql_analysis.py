"""
Management command to test CodeQL analysis for a specific repository
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from repositories.models import Repository
from analytics.codeql_indexing_service import get_codeql_indexing_service_for_user
from analytics.models import CodeQLVulnerability
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command for testing CodeQL analysis"""
    
    help = 'Test CodeQL security analysis for a specific repository'

    def add_arguments(self, parser):
        parser.add_argument(
            'repo_name',
            type=str,
            help='Repository name in format "owner/repo" (e.g., "microsoft/vscode")'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reanalysis even if recently analyzed'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed vulnerability information'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing CodeQL data for this repository before analysis'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be analyzed without actually running the analysis'
        )

    def handle(self, *args, **options):
        """Execute the command"""
        repo_name = options['repo_name']
        force = options['force']
        verbose = options['verbose']
        clear = options['clear']
        dry_run = options['dry_run']
        
        # Set up console logging for this command
        console_handler = logging.StreamHandler(self.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        
        self.stdout.write(
            self.style.SUCCESS(f'Testing CodeQL analysis for repository: {repo_name}')
        )
        
        try:
            # Find repository
            repository = self._find_repository(repo_name)
            
            if dry_run:
                self._show_dry_run_info(repository, force)
                return
            
            # Clear existing data if requested
            if clear:
                self._clear_existing_data(repo_name)
            
            # Run CodeQL analysis
            results = self._run_codeql_analysis(repository, force)
            
            # Display results
            self._display_results(results, verbose)
            
            # Show summary
            self._show_summary(repo_name)
            
        except Exception as e:
            raise CommandError(f'CodeQL analysis failed: {e}')

    def _find_repository(self, repo_name):
        """Find repository by name"""
        try:
            repository = Repository.objects.get(full_name=repo_name)
            self.stdout.write(f'Found repository: {repository.full_name} (ID: {repository.id})')
            return repository
        except Repository.DoesNotExist:
            raise CommandError(
                f'Repository "{repo_name}" not found. '
                f'Make sure it exists and is properly formatted as "owner/repo"'
            )

    def _clear_existing_data(self, repo_name):
        """Clear existing CodeQL data for repository"""
        existing_count = CodeQLVulnerability.objects(repository_full_name=repo_name).count()
        if existing_count > 0:
            self.stdout.write(f'Clearing {existing_count} existing CodeQL vulnerabilities...')
            CodeQLVulnerability.objects(repository_full_name=repo_name).delete()
            self.stdout.write(self.style.SUCCESS('Existing data cleared successfully'))
        else:
            self.stdout.write('No existing CodeQL data found')

    def _run_codeql_analysis(self, repository, force):
        """Run CodeQL analysis for repository"""
        self.stdout.write('Starting CodeQL analysis...')
        
        # Get indexing service
        indexing_service = get_codeql_indexing_service_for_user(repository.owner.id)
        
        # Run analysis
        results = indexing_service.index_codeql_for_repository(
            repository_id=repository.id,
            repository_full_name=repository.full_name,
            force_reindex=force
        )
        
        return results

    def _display_results(self, results, verbose):
        """Display analysis results"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('CODEQL ANALYSIS RESULTS')
        self.stdout.write('='*60)
        
        status = results.get('status', 'unknown')
        if status == 'success':
            self.stdout.write(self.style.SUCCESS(f'Status: {status.upper()}'))
        elif status == 'error':
            self.stdout.write(self.style.ERROR(f'Status: {status.upper()}'))
        else:
            self.stdout.write(self.style.WARNING(f'Status: {status.upper()}'))
        
        # Show metrics
        self.stdout.write(f'Repository: {results.get("repository_full_name", "N/A")}')
        self.stdout.write(f'Vulnerabilities processed: {results.get("vulnerabilities_processed", 0)}')
        self.stdout.write(f'New vulnerabilities: {results.get("vulnerabilities_new", 0)}')
        self.stdout.write(f'Updated vulnerabilities: {results.get("vulnerabilities_updated", 0)}')
        self.stdout.write(f'Removed vulnerabilities: {results.get("vulnerabilities_removed", 0)}')
        
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

    def _show_summary(self, repo_name):
        """Show summary of current vulnerability state"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('VULNERABILITY SUMMARY')
        self.stdout.write('='*60)
        
        # Get all vulnerabilities for this repository
        vulnerabilities = list(CodeQLVulnerability.objects(repository_full_name=repo_name))
        
        if not vulnerabilities:
            self.stdout.write(self.style.SUCCESS('No vulnerabilities found! 🎉'))
            return
        
        # Count by severity
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        state_counts = {'open': 0, 'fixed': 0, 'dismissed': 0}
        category_counts = {}
        
        for vuln in vulnerabilities:
            severity_counts[vuln.severity] += 1
            state_counts[vuln.state] += 1
            category = vuln.category or 'other'
            category_counts[category] = category_counts.get(category, 0) + 1
        
        # Display severity breakdown
        self.stdout.write(f'Total vulnerabilities: {len(vulnerabilities)}')
        self.stdout.write('\nBy severity:')
        for severity, count in severity_counts.items():
            if count > 0:
                color = self._get_severity_style(severity)
                self.stdout.write(f'  {severity.title()}: {color(str(count))}')
        
        # Display state breakdown
        self.stdout.write('\nBy state:')
        for state, count in state_counts.items():
            if count > 0:
                color = self._get_state_style(state)
                self.stdout.write(f'  {state.title()}: {color(str(count))}')
        
        # Display top categories
        if category_counts:
            self.stdout.write('\nTop vulnerability categories:')
            sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            for category, count in sorted_categories[:5]:
                self.stdout.write(f'  {category}: {count}')
        
        # Calculate and show security score
        from analytics.codeql_service import CodeQLService
        codeql_service = CodeQLService()
        metrics = codeql_service.calculate_security_score(vulnerabilities)
        score = metrics.get('score', 0)
        
        self.stdout.write(f'\nSecurity Score: {self._get_score_style(score)(str(score))}/100')
        
        # Show recent vulnerabilities
        recent_vulns = [v for v in vulnerabilities if v.get_age_days() <= 7]
        if recent_vulns:
            self.stdout.write(f'\nRecent vulnerabilities (last 7 days): {len(recent_vulns)}')

    def _show_dry_run_info(self, repository, force):
        """Show what would be analyzed in dry run mode"""
        self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual analysis will be performed'))
        self.stdout.write(f'Repository: {repository.full_name} (ID: {repository.id})')
        self.stdout.write(f'Owner: {repository.owner.username if repository.owner else "Unknown"}')
        self.stdout.write(f'Force reindex: {"Yes" if force else "No"}')
        
        # Check existing data
        existing_count = CodeQLVulnerability.objects(repository_full_name=repository.full_name).count()
        self.stdout.write(f'Existing vulnerabilities: {existing_count}')
        
        # Check if reindex is needed
        from analytics.codeql_indexing_service import get_codeql_indexing_service_for_user
        indexing_service = get_codeql_indexing_service_for_user(repository.owner.id)
        should_reindex = indexing_service.should_reindex(repository.full_name, force)
        self.stdout.write(f'Should reindex: {"Yes" if should_reindex else "No"}')
        
        if not should_reindex and not force:
            self.stdout.write(self.style.WARNING(
                'Analysis would be skipped (recently analyzed). Use --force to override.'
            ))

    def _get_severity_style(self, severity):
        """Get style for severity display"""
        styles = {
            'critical': self.style.ERROR,
            'high': self.style.WARNING,
            'medium': self.style.HTTP_NOT_MODIFIED,
            'low': self.style.HTTP_INFO
        }
        return styles.get(severity, self.style.SUCCESS)

    def _get_state_style(self, state):
        """Get style for state display"""
        styles = {
            'open': self.style.ERROR,
            'fixed': self.style.SUCCESS,
            'dismissed': self.style.WARNING
        }
        return styles.get(state, self.style.SUCCESS)

    def _get_score_style(self, score):
        """Get style for score display"""
        if score >= 80:
            return self.style.SUCCESS
        elif score >= 60:
            return self.style.WARNING
        else:
            return self.style.ERROR