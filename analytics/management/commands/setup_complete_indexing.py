"""
Management command to set up complete indexing system for repositories
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from repositories.models import Repository
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Set up complete indexing system for repositories (commits, PRs, releases, developers, SBOMs)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--time',
            default='02:00',
            help='Time to run indexing (HH:MM format, default: 02:00)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate all schedules',
        )
        parser.add_argument(
            '--spread',
            action='store_true',
            help='Spread tasks across different times to avoid conflicts',
        )

    def handle(self, *args, **options):
        run_time = options['time']
        force = options['force']
        spread = options['spread']
        
        try:
            hour, minute = map(int, run_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time format")
        except ValueError:
            self.stdout.write(
                self.style.ERROR(f'Invalid time format: {run_time}. Use HH:MM format.')
            )
            return
        
        # Check if we have indexed repositories
        indexed_repos = Repository.objects.filter(is_indexed=True)
        if not indexed_repos.exists():
            self.stdout.write(
                self.style.WARNING('No indexed repositories found. Index some repositories first.')
            )
            return
        
        self.stdout.write(f'Setting up complete indexing system for {indexed_repos.count()} repositories...')
        
        # Clear existing schedules if force
        if force:
            self._clear_existing_schedules()
        
        # Setup all tasks
        self._setup_commit_indexing(hour, minute, spread)
        self._setup_pr_indexing(hour, minute, spread)
        self._setup_release_indexing(hour, minute, spread)
        self._setup_quality_analysis(hour, minute, spread)
        self._setup_developer_grouping(hour, minute, spread)
        self._setup_sbom_generation(hour, minute, spread)
        
        self.stdout.write(
            self.style.SUCCESS('Complete indexing system setup finished!')
        )
        
        # Show summary
        self._show_summary()
    
    def _clear_existing_schedules(self):
        """Clear existing indexing schedules"""
        schedules_to_delete = Schedule.objects.filter(
            name__in=[
                'daily_indexing_all_repos',
                'daily_pr_indexing',
                'daily_release_indexing', 
                'daily_quality_analysis',
                'daily_developer_grouping',
                'daily_sbom_generation'
            ]
        )
        deleted_count = schedules_to_delete.count()
        schedules_to_delete.delete()
        if deleted_count > 0:
            self.stdout.write(f'Deleted {deleted_count} existing schedules.')
    
    def _setup_commit_indexing(self, hour, minute, spread):
        """Setup daily commit indexing"""
        schedule_name = "daily_indexing_all_repos"
        next_run = self._get_next_run_time(hour, minute)
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.daily_indexing_all_repos_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.daily_indexing_all_repos_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Commit indexing scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _setup_pr_indexing(self, hour, minute, spread):
        """Setup daily PR indexing"""
        schedule_name = "daily_pr_indexing"
        next_run = self._get_next_run_time(hour, minute + (15 if spread else 0))
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.fetch_all_pull_requests_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.fetch_all_pull_requests_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ PR indexing scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _setup_release_indexing(self, hour, minute, spread):
        """Setup daily release indexing"""
        schedule_name = "daily_release_indexing"
        # Calculate time with proper hour/minute handling
        if spread:
            # Add 30 minutes to the base time
            adjusted_hour = hour
            adjusted_minute = minute + 30
            if adjusted_minute >= 60:
                adjusted_hour = (adjusted_hour + 1) % 24
                adjusted_minute = adjusted_minute % 60
        else:
            adjusted_hour = hour
            adjusted_minute = minute
        next_run = self._get_next_run_time(adjusted_hour, adjusted_minute)
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.release_indexing_all_repos_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.release_indexing_all_repos_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Release indexing scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _setup_quality_analysis(self, hour, minute, spread):
        """Setup daily quality analysis"""
        schedule_name = "daily_quality_analysis"
        # Calculate time with proper hour/minute handling
        if spread:
            # Add 45 minutes to the base time
            adjusted_hour = hour
            adjusted_minute = minute + 45
            if adjusted_minute >= 60:
                adjusted_hour = (adjusted_hour + 1) % 24
                adjusted_minute = adjusted_minute % 60
        else:
            adjusted_hour = hour
            adjusted_minute = minute
        next_run = self._get_next_run_time(adjusted_hour, adjusted_minute)
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.quality_analysis_all_repos_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.quality_analysis_all_repos_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Quality analysis scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _setup_developer_grouping(self, hour, minute, spread):
        """Setup daily developer grouping"""
        schedule_name = "daily_developer_grouping"
        # Calculate time with proper hour/minute handling
        if spread:
            # Add 1 hour to the base time
            adjusted_hour = (hour + 1) % 24
            adjusted_minute = minute
        else:
            adjusted_hour = hour
            adjusted_minute = minute
        next_run = self._get_next_run_time(adjusted_hour, adjusted_minute)
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.group_developer_identities_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.group_developer_identities_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Developer grouping scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _setup_sbom_generation(self, hour, minute, spread):
        """Setup daily SBOM generation"""
        schedule_name = "daily_sbom_generation"
        # Calculate time with proper hour/minute handling
        if spread:
            # Add 1.5 hours to the base time
            adjusted_hour = (hour + 1) % 24
            adjusted_minute = minute + 30
            if adjusted_minute >= 60:
                adjusted_hour = (adjusted_hour + 1) % 24
                adjusted_minute = adjusted_minute % 60
        else:
            adjusted_hour = hour
            adjusted_minute = minute
        next_run = self._get_next_run_time(adjusted_hour, adjusted_minute)
        
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.check_new_releases_and_generate_sbom_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,
                'next_run': next_run,
            }
        )
        
        if not created:
            schedule.func = 'analytics.tasks.check_new_releases_and_generate_sbom_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ SBOM generation scheduled at {next_run.strftime("%H:%M")}')
        )
    
    def _get_next_run_time(self, hour, minute):
        """Calculate next run time for the given hour and minute"""
        now = timezone.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run
    
    def _show_summary(self):
        """Show summary of all scheduled tasks"""
        indexing_tasks = Schedule.objects.filter(
            name__in=[
                'daily_indexing_all_repos',
                'daily_pr_indexing',
                'daily_release_indexing',
                'daily_quality_analysis', 
                'daily_developer_grouping',
                'daily_sbom_generation'
            ]
        )
        
        self.stdout.write('')
        self.stdout.write('📋 Indexing Schedule Summary:')
        self.stdout.write('=' * 50)
        
        for task in indexing_tasks:
            status = '✅ Active' if task.next_run else '❌ Inactive'
            self.stdout.write(f'{task.name}: {task.func} | {status}')
        
        self.stdout.write('')
        self.stdout.write('🔄 Daily Workflow:')
        self.stdout.write('1. Commit indexing (02:00)')
        self.stdout.write('2. PR indexing (02:15)') 
        self.stdout.write('3. Release indexing (02:30)')
        self.stdout.write('4. Quality analysis (02:45)')
        self.stdout.write('5. Developer grouping (03:00)')
        self.stdout.write('6. SBOM generation (03:30)')
        self.stdout.write('')
        self.stdout.write('💡 Use --spread to distribute tasks across different times') 