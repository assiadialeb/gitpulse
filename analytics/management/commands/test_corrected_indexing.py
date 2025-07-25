"""
Command to test the corrected indexing system
"""
from django.core.management.base import BaseCommand
from analytics.tasks import index_all_commits_task


class Command(BaseCommand):
    help = 'Test the corrected indexing system by calling index_all_commits_task'

    def handle(self, *args, **options):
        self.stdout.write("Testing corrected indexing system...")
        
        try:
            result = index_all_commits_task()
            
            self.stdout.write("✅ index_all_commits_task completed successfully!")
            self.stdout.write(f"Result: {result}")
            
            # Check if tasks were scheduled
            scheduled_count = result.get('successfully_scheduled', 0)
            failed_count = result.get('failed_to_schedule', 0)
            
            if scheduled_count > 0:
                self.stdout.write(self.style.SUCCESS(f"✅ Successfully scheduled {scheduled_count} commit indexing tasks"))
            
            if failed_count > 0:
                self.stdout.write(self.style.WARNING(f"⚠️  Failed to schedule {failed_count} tasks"))
            
            self.stdout.write("\nNow check the Q worker logs to see if the tasks execute without argument errors!")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error calling index_all_commits_task: {e}")) 