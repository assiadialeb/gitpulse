"""
Command to restart Django-Q worker
"""
from django.core.management.base import BaseCommand
import subprocess
import time
import os


class Command(BaseCommand):
    help = 'Restart Django-Q worker'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Restarting Django-Q worker...")
        
        # Kill existing worker processes
        try:
            subprocess.run(['pkill', '-f', 'manage.py qcluster'], check=False)
            self.stdout.write("✅ Killed existing worker processes")
        except:
            self.stdout.write("ℹ️  No existing worker processes found")
        
        # Wait a moment
        time.sleep(2)
        
        # Start new worker
        try:
            # Start worker in background
            subprocess.Popen([
                'python', 'manage.py', 'qcluster'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            self.stdout.write("✅ Started new Django-Q worker")
            self.stdout.write("⏳ Waiting 3 seconds for worker to initialize...")
            time.sleep(3)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to start worker: {e}"))
            return
        
        self.stdout.write(self.style.SUCCESS("✅ Worker restarted successfully!")) 