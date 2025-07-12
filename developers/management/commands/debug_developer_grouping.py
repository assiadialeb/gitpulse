from django.core.management.base import BaseCommand
from applications.models import Application
from analytics.analytics_service import AnalyticsService
from analytics.models import Commit


class Command(BaseCommand):
    help = 'Debug developer grouping functionality'

    def handle(self, *args, **options):
        self.stdout.write("=== Developer Grouping Debug ===\n")
        
        # Get all applications
        applications = Application.objects.all()
        self.stdout.write(f"Found {applications.count()} applications\n")
        
        # Check commits in database
        total_commits = Commit.objects.count()
        self.stdout.write(f"Total commits in database: {total_commits}\n")
        
        if total_commits == 0:
            self.stdout.write(self.style.WARNING("No commits found in database!"))
            return
        
        # Get unique developers from commits
        unique_developers = set()
        for commit in Commit.objects.all()[:100]:  # Check first 100 commits
            dev_key = f"{commit.author_name}|{commit.author_email}"
            unique_developers.add(dev_key)
        
        self.stdout.write(f"Unique developers from commits (first 100): {len(unique_developers)}\n")
        for dev in list(unique_developers)[:5]:  # Show first 5
            self.stdout.write(f"  - {dev}\n")
        
        # Check what developers are shown in the UI
        self.stdout.write("\n=== Developers shown in UI ===\n")
        
        for application in applications:
            self.stdout.write(f"\nApplication: {application.name} (ID: {application.id})\n")
            
            analytics = AnalyticsService(application.id)
            
            # Get grouped developers
            grouped_devs = analytics.get_grouped_developers()
            self.stdout.write(f"  Grouped developers: {len(grouped_devs)}\n")
            
            # Get individual developers
            individual_devs = analytics.get_individual_developers()
            self.stdout.write(f"  Individual developers: {len(individual_devs)}\n")
            
            if individual_devs:
                self.stdout.write("  Sample individual developers:\n")
                for dev in individual_devs[:3]:
                    self.stdout.write(f"    - {dev['name']} ({dev['email']}) - {dev['commit_count']} commits\n")
        
        # Test the grouping service directly
        self.stdout.write("\n=== Testing Grouping Service ===\n")
        
        from analytics.developer_grouping_service import DeveloperGroupingService
        grouping_service = DeveloperGroupingService()
        
        # Get all developers from commits
        all_commits = Commit.objects.all()
        all_developers = grouping_service._extract_unique_developers(all_commits)
        
        self.stdout.write(f"Total unique developers from all commits: {len(all_developers)}\n")
        
        if all_developers:
            self.stdout.write("Sample developers:\n")
            for dev in all_developers[:5]:
                self.stdout.write(f"  - {dev['name']} ({dev['email']}) - {dev['commit_count']} commits\n")
        
        # Test manual grouping with sample data
        if len(all_developers) >= 2:
            sample_devs = all_developers[:2]
            dev_keys = [f"{dev['name']}|{dev['email']}" for dev in sample_devs]
            
            self.stdout.write(f"\nTesting manual grouping with: {dev_keys}\n")
            
            group_data = {
                'primary_name': 'Test Group',
                'primary_email': 'test@example.com',
                'developer_ids': dev_keys
            }
            
            result = grouping_service.manually_group_developers(group_data)
            self.stdout.write(f"Result: {result}\n") 