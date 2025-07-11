"""
Management command to set up rate limit monitoring tasks
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Set up rate limit monitoring tasks'

    def handle(self, *args, **options):
        self.stdout.write('Setting up rate limit monitoring tasks...')
        
        try:
            # Create task to process pending rate limit restarts every 5 minutes
            schedule, created = Schedule.objects.get_or_create(
                name='process_pending_rate_limit_restarts',
                defaults={
                    'func': 'analytics.services.process_pending_rate_limit_restarts',
                    'schedule_type': Schedule.MINUTES,
                    'minutes': 5,
                    'next_run': datetime.now() + timedelta(minutes=1),
                    'repeats': -1  # Infinite repeats
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS('Created rate limit monitoring task')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Rate limit monitoring task already exists')
                )
            
            # Create task to clean up old rate limit resets (older than 7 days)
            cleanup_schedule, cleanup_created = Schedule.objects.get_or_create(
                name='cleanup_old_rate_limit_resets',
                defaults={
                    'func': 'analytics.services.cleanup_old_rate_limit_resets',
                    'schedule_type': Schedule.DAILY,
                    'next_run': datetime.now().replace(hour=2, minute=0, second=0, microsecond=0),
                    'repeats': -1  # Infinite repeats
                }
            )
            
            if cleanup_created:
                self.stdout.write(
                    self.style.SUCCESS('Created rate limit cleanup task')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Rate limit cleanup task already exists')
                )
            
            self.stdout.write(
                self.style.SUCCESS('Rate limit monitoring setup completed successfully')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to set up rate limit monitoring: {e}')
            ) 