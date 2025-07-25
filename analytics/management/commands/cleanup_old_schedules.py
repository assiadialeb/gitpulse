"""
Management command to clean up old application-based schedules
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule


class Command(BaseCommand):
    help = 'Clean up old application-based scheduled tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find all old application-based schedules
        old_schedules = Schedule.objects.filter(
            name__startswith='daily_indexing_'
        ).exclude(
            name__startswith='daily_indexing_repo_'
        ).exclude(
            name='daily_indexing_all_repos'
        )
        
        # Also find schedules with old function names
        old_function_schedules = Schedule.objects.filter(
            func__in=[
                'analytics.tasks.release_indexing_all_apps_task',
                'analytics.tasks.daily_indexing_all_apps_task'
            ]
        )
        
        all_old_schedules = (old_schedules | old_function_schedules).distinct()
        
        if not all_old_schedules.exists():
            self.stdout.write(self.style.SUCCESS('No old schedules found to clean up.'))
            return
        
        self.stdout.write(f'Found {all_old_schedules.count()} old schedules to clean up:')
        self.stdout.write('=' * 60)
        
        for schedule in all_old_schedules:
            self.stdout.write(f'- {schedule.name} ({schedule.func})')
        
        self.stdout.write('=' * 60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No schedules were actually deleted. Use without --dry-run to delete.')
            )
            return
        
        # Delete old schedules
        deleted_count = all_old_schedules.count()
        all_old_schedules.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {deleted_count} old schedules.')
        )
        
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('1. Set up new repository-based indexing:')
        self.stdout.write('   python manage.py setup_repository_indexing --global-task --time 02:00')
        self.stdout.write('')
        self.stdout.write('2. Or set up individual repository tasks:')
        self.stdout.write('   python manage.py setup_repository_indexing --time 02:00')
        self.stdout.write('')
        self.stdout.write('3. Set up release indexing:')
        self.stdout.write('   python manage.py shell -c "from django_q.models import Schedule; Schedule.objects.get_or_create(name=\'daily_release_indexing\', defaults={\'func\': \'analytics.tasks.release_indexing_all_repos_task\', \'schedule_type\': \'D\', \'repeats\': -1})"') 