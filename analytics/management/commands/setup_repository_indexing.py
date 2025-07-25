"""
Management command to set up automatic indexing for repositories
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from repositories.models import Repository
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Set up automatic daily indexing for repositories'

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
            '--global-task',
            action='store_true',
            help='Create a single global task instead of individual repository tasks',
        )

    def handle(self, *args, **options):
        run_time = options['time']
        force = options['force']
        global_task = options['global_task']
        
        try:
            hour, minute = map(int, run_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time format")
        except ValueError:
            self.stdout.write(
                self.style.ERROR(f'Invalid time format: {run_time}. Use HH:MM format.')
            )
            return
        
        if global_task:
            self._setup_global_task(hour, minute, force)
        else:
            self._setup_individual_tasks(hour, minute, force)
    
    def _setup_global_task(self, hour, minute, force):
        """Setup a single global task that processes all repositories"""
        schedule_name = "daily_indexing_all_repos"
        
        # Check if schedule already exists
        existing_schedule = Schedule.objects.filter(name=schedule_name).first()
        
        if existing_schedule and not force:
            self.stdout.write(
                'Global repository indexing schedule already exists. Use --force to recreate.'
            )
            return
        
        # Calculate next run time
        next_run = self._get_next_run_time(hour, minute)
        
        # Create or update schedule
        schedule, created = Schedule.objects.get_or_create(
            name=schedule_name,
            defaults={
                'func': 'analytics.tasks.daily_indexing_all_repos_task',
                'schedule_type': Schedule.DAILY,
                'repeats': -1,  # Repeat indefinitely
                'next_run': next_run,
            }
        )
        
        if not created and force:
            # Update existing schedule
            schedule.func = 'analytics.tasks.daily_indexing_all_repos_task'
            schedule.schedule_type = Schedule.DAILY
            schedule.repeats = -1
            schedule.next_run = next_run
            schedule.save()
            self.stdout.write(
                self.style.SUCCESS(f'Updated global repository indexing schedule (runs at {hour:02d}:{minute:02d})')
            )
        elif created:
            self.stdout.write(
                self.style.SUCCESS(f'Created global repository indexing schedule (runs at {hour:02d}:{minute:02d})')
            )
        
        # Count repositories that will be indexed
        indexed_repos = Repository.objects.filter(is_indexed=True).count()
        self.stdout.write(f'This schedule will process {indexed_repos} indexed repositories daily.')
    
    def _setup_individual_tasks(self, hour, minute, force):
        """Setup individual tasks for each repository"""
        # Get all indexed repositories
        repositories = Repository.objects.filter(is_indexed=True)
        
        if not repositories.exists():
            self.stdout.write(
                self.style.WARNING('No indexed repositories found. Index some repositories first.')
            )
            return
        
        schedules_created = 0
        schedules_updated = 0
        
        for repository in repositories:
            schedule_name = f"daily_indexing_repo_{repository.id}"
            
            # Check if schedule already exists
            existing_schedule = Schedule.objects.filter(name=schedule_name).first()
            
            if existing_schedule and not force:
                self.stdout.write(
                    f'Schedule for repository "{repository.full_name}" already exists. Use --force to recreate.'
                )
                continue
            
            # Calculate next run time with slight delay to avoid conflicts
            delay_minutes = schedules_created % 60  # Spread tasks across the hour
            next_run = self._get_next_run_time(hour, minute + delay_minutes)
            
            # Create or update schedule
            schedule, created = Schedule.objects.get_or_create(
                name=schedule_name,
                defaults={
                    'func': 'analytics.tasks.background_indexing_task',
                    'args': [repository.id, repository.owner_id],
                    'schedule_type': Schedule.DAILY,
                    'repeats': -1,  # Repeat indefinitely
                    'next_run': next_run,
                }
            )
            
            if not created and force:
                # Update existing schedule
                schedule.func = 'analytics.tasks.background_indexing_task'
                schedule.args = [repository.id, repository.owner_id]
                schedule.schedule_type = Schedule.DAILY
                schedule.repeats = -1
                schedule.next_run = next_run
                schedule.save()
                schedules_updated += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Updated schedule for repository "{repository.full_name}" (runs at {next_run.strftime("%H:%M")})')
                )
            elif created:
                schedules_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created schedule for repository "{repository.full_name}" (runs at {next_run.strftime("%H:%M")})')
                )
        
        total_schedules = schedules_created + schedules_updated
        self.stdout.write(
            self.style.SUCCESS(f'Setup complete! {total_schedules} repository schedules configured.')
        )
        
        if schedules_created > 0:
            self.stdout.write(f'Created {schedules_created} new schedules.')
        if schedules_updated > 0:
            self.stdout.write(f'Updated {schedules_updated} existing schedules.')
    
    def _get_next_run_time(self, hour, minute):
        """Calculate next run time for the given hour and minute"""
        now = timezone.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run 