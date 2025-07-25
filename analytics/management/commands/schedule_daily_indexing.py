"""
Management command to schedule daily indexing for all applications
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule

from analytics.tasks import background_indexing_task
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Schedule daily indexing for all applications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate schedules even if they already exist',
        )

    def handle(self, *args, **options):
        force = options['force']
        
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
            
            # Create or update schedule
            schedule, created = Schedule.objects.get_or_create(
                name=schedule_name,
                defaults={
                    'func': 'analytics.tasks.background_indexing_task',
                    'args': [application.id],
                    'schedule_type': Schedule.DAILY,
                    'repeats': -1,  # Repeat indefinitely
                    'next_run': self._get_next_run_time(),
                }
            )
            
            if not created and force:
                # Update existing schedule
                schedule.func = 'analytics.tasks.background_indexing_task'
                schedule.args = [application.id]
                schedule.schedule_type = Schedule.DAILY
                schedule.repeats = -1
                schedule.next_run = self._get_next_run_time()
                schedule.save()
                schedules_updated += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Updated schedule for application "{application.name}"')
                )
            elif created:
                schedules_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created schedule for application "{application.name}"')
                )
        
        total_schedules = schedules_created + schedules_updated
        
        if total_schedules > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully scheduled daily indexing for {total_schedules} application(s)'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('No new schedules were created.')
            )
    
    def _get_next_run_time(self):
        """Get the next run time (tomorrow at 2 AM UTC)"""
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        now = timezone.now()
        tomorrow = now + timedelta(days=1)
        next_run = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)
        
        return next_run 