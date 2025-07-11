"""
Management command to list and manage scheduled tasks
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from applications.models import Application


class Command(BaseCommand):
    help = 'List and manage scheduled tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Delete all scheduled indexing tasks',
        )
        parser.add_argument(
            '--application-id',
            type=int,
            help='Filter by specific application ID',
        )

    def handle(self, *args, **options):
        delete_mode = options['delete']
        application_id = options['application_id']
        
        if delete_mode:
            self._delete_schedules(application_id)
        else:
            self._list_schedules(application_id)
    
    def _list_schedules(self, application_id=None):
        """List all scheduled tasks"""
        schedules = Schedule.objects.all()
        
        if application_id:
            schedules = schedules.filter(name__startswith=f"daily_indexing_{application_id}")
        
        if not schedules.exists():
            self.stdout.write('No scheduled tasks found.')
            return
        
        self.stdout.write('Scheduled Tasks:')
        self.stdout.write('=' * 80)
        
        for schedule in schedules:
            status = 'Active' if schedule.next_run else 'Inactive'
            self.stdout.write(
                f'Name: {schedule.name}\n'
                f'Function: {schedule.func}\n'
                f'Arguments: {schedule.args}\n'
                f'Schedule Type: {schedule.schedule_type}\n'
                f'Next Run: {schedule.next_run}\n'
                f'Repeats: {schedule.repeats}\n'
                f'Status: {status}\n'
                f'{("-" * 40)}'
            )
    
    def _delete_schedules(self, application_id=None):
        """Delete scheduled tasks"""
        schedules = Schedule.objects.filter(name__startswith='daily_indexing_')
        
        if application_id:
            schedules = schedules.filter(name__startswith=f"daily_indexing_{application_id}")
        
        if not schedules.exists():
            self.stdout.write('No scheduled indexing tasks found to delete.')
            return
        
        count = schedules.count()
        schedules.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {count} scheduled task(s).')
        ) 