"""
Management command to test analytics service
"""
from django.core.management.base import BaseCommand
from analytics.analytics_service import AnalyticsService


class Command(BaseCommand):
    help = 'Test analytics service for an application'

    def add_arguments(self, parser):
        parser.add_argument('application_id', type=int, help='Application ID to test')

    def handle(self, *args, **options):
        application_id = options['application_id']
        
        self.stdout.write(f"Testing analytics service for application {application_id}")
        
        try:
            # Initialize analytics service
            analytics = AnalyticsService(application_id)
            
            # Test overall stats
            self.stdout.write("Testing get_overall_stats()...")
            overall_stats = analytics.get_overall_stats()
            self.stdout.write(f"✓ Overall stats: {overall_stats}")
            
            # Test developer activity
            self.stdout.write("Testing get_developer_activity()...")
            dev_activity = analytics.get_developer_activity(days=30)
            self.stdout.write(f"✓ Developer activity: {dev_activity}")
            
            # Test activity heatmap
            self.stdout.write("Testing get_activity_heatmap()...")
            heatmap = analytics.get_activity_heatmap(days=90)
            self.stdout.write(f"✓ Activity heatmap: {heatmap}")
            
            # Test code distribution
            self.stdout.write("Testing get_code_distribution()...")
            distribution = analytics.get_code_distribution()
            self.stdout.write(f"✓ Code distribution: {distribution}")
            
            # Test commit quality
            self.stdout.write("Testing get_commit_quality_metrics()...")
            quality = analytics.get_commit_quality_metrics()
            self.stdout.write(f"✓ Commit quality: {quality}")
            
            self.stdout.write(
                self.style.SUCCESS('✓ All analytics service methods executed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Error testing analytics service: {e}')
            )
            raise 