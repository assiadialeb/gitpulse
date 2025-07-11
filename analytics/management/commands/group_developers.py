"""
Management command to group developers with multiple identities
"""
from django.core.management.base import BaseCommand
from analytics.analytics_service import AnalyticsService


class Command(BaseCommand):
    help = 'Group developers with multiple usernames/emails'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to group developers for')
        parser.add_argument('--force', action='store_true', help='Force re-grouping of developers')

    def handle(self, *args, **options):
        application_id = options['application_id']
        force = options['force']
        
        self.stdout.write(f"Grouping developers for application {application_id}")
        
        try:
            # Initialize analytics service
            analytics = AnalyticsService(application_id)
            
            # Group developers
            self.stdout.write("Running developer grouping...")
            results = analytics.group_developers()
            
            self.stdout.write(f"✓ Found {results['total_developers']} unique developers")
            self.stdout.write(f"✓ Created {results['groups_created']} developer groups")
            
            # Show grouped developers
            self.stdout.write("\nGrouped developers:")
            grouped_devs = analytics.get_grouped_developers()
            
            for group in grouped_devs:
                self.stdout.write(f"\n📊 {group['primary_name']} ({group['primary_email']})")
                self.stdout.write(f"   Confidence: {group['confidence_score']}%")
                self.stdout.write(f"   Total commits: {group['total_commits']}")
                self.stdout.write(f"   Aliases: {len(group['aliases'])}")
                
                for alias in group['aliases']:
                    self.stdout.write(f"   - {alias['name']} ({alias['email']}) - {alias['commit_count']} commits")
            
            # Test updated analytics
            self.stdout.write("\nTesting updated analytics...")
            
            # Test developer activity
            dev_activity = analytics.get_developer_activity(days=30)
            self.stdout.write(f"✓ Developer activity: {len(dev_activity['developers'])} developers")
            
            # Test code distribution
            distribution = analytics.get_code_distribution()
            self.stdout.write(f"✓ Code distribution: {len(distribution['distribution'])} developers")
            
            # Test overall stats
            overall_stats = analytics.get_overall_stats()
            self.stdout.write(f"✓ Overall stats: {overall_stats['total_authors']} unique authors")
            
            self.stdout.write("\n✅ Developer grouping completed successfully!")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            raise 