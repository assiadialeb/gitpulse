"""
Management command to set up automatic indexing for new applications
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule

from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Set up automatic daily indexing for new applications'

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

    def handle(self, *args, **options):
        run_time = options['time']
        force = options['force']
        
        try:
            hour, minute = map(int, run_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time format")
        except ValueError:
            self.stdout.write(
                self.style.ERROR(f'Invalid time format: {run_time}. Use HH:MM format.')
            )
            return
        
        # Get all applications
        applications = Application.objects.all()
        
        if not applications.exists():
            self.stdout.write(
                self.style.WARNING('No applications found. Create some applications first.')
            )
            return
        
        schedules_created = 0
        schedules_updated = 0
        
        for application in applications:
            schedule_name = f"daily_indexing_{application.id}"
            
            # Check if schedule already exists
            existing_schedule = Schedule.objects.filter(name=schedule_name).first()
            
            if existing_schedule and not force:
                self.stdout.write(
                    f'Schedule for application "{application.name}" already exists. Use --force to recreate.'
                )
                continue
            
            # Calculate next run time
            next_run = self._get_next_run_time(hour, minute)
            
            # Create or update schedule
            schedule, created = Schedule.objects.get_or_create(
                name=schedule_name,
                defaults={
                    'func': 'analytics.tasks.background_indexing_task',
                    'args': [application.id],
                    'schedule_type': Schedule.DAILY,
                    'repeats': -1,  # Repeat indefinitely
                    'next_run': next_run,
                }
            )
            
            if not created and force:
                # Update existing schedule
                schedule.func = 'analytics.tasks.background_indexing_task'
                schedule.args = [application.id]
                schedule.schedule_type = Schedule.DAILY
                schedule.repeats = -1
                schedule.next_run = next_run
                schedule.save()
                schedules_updated += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Updated schedule for application "{application.name}" (runs at {run_time})')
                )
            elif created:
                schedules_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created schedule for application "{application.name}" (runs at {run_time})')
                )
        
        total_schedules = schedules_created + schedules_updated
        
        if total_schedules > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully set up daily indexing for {total_schedules} application(s)'
                )
            )
            self.stdout.write(
                f'Indexing will run daily at {run_time} UTC'
            )
        else:
            self.stdout.write(
                self.style.WARNING('No new schedules were created.')
            )
    
    def _get_next_run_time(self, hour, minute):
        """Get the next run time at the specified hour and minute"""
        now = timezone.now()
        
        # Set the time for today
        today_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If the time has already passed today, schedule for tomorrow
        if today_run <= now:
            tomorrow_run = today_run + timedelta(days=1)
            return tomorrow_run
        
        return today_run 