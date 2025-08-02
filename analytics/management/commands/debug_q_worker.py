#!/usr/bin/env python3
"""
Django management command to debug Django-Q worker issues
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule, Success, Failure
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Debug Django-Q worker issues'

    def handle(self, *args, **options):
        self.stdout.write("🔍 Debugging Django-Q worker...")
        
        # Check scheduled tasks
        now = timezone.now()
        scheduled_tasks = Schedule.objects.all()
        overdue_tasks = Schedule.objects.filter(next_run__lt=now)
        pending_tasks = Schedule.objects.filter(next_run__lte=now)
        
        self.stdout.write(f"\n📋 Scheduled Tasks: {scheduled_tasks.count()}")
        for task in scheduled_tasks:
            self.stdout.write(f"  - {task.name}: {task.func} (next: {task.next_run})")
        
        self.stdout.write(f"\n⚠️  Overdue Tasks: {overdue_tasks.count()}")
        for task in overdue_tasks:
            self.stdout.write(f"  - {task.name}: {task.func} (was due: {task.next_run})")
        
        self.stdout.write(f"\n⏳ Pending Tasks: {pending_tasks.count()}")
        for task in pending_tasks:
            self.stdout.write(f"  - {task.name}: {task.func} (due: {task.next_run})")
        
        # Check recent task execution
        recent = now - timedelta(minutes=10)
        recent_success = Success.objects.filter(started__gte=recent)
        recent_failures = Failure.objects.filter(started__gte=recent)
        
        self.stdout.write(f"\n✅ Recent Successes: {recent_success.count()}")
        for task in recent_success[:5]:  # Show last 5
            self.stdout.write(f"  - {task.func}: {task.result[:100] if task.result else 'No result'}")
        
        self.stdout.write(f"\n❌ Recent Failures: {recent_failures.count()}")
        for task in recent_failures[:5]:  # Show last 5
            self.stdout.write(f"  - {task.func}: {task.error[:100] if task.error else 'No error'}")
        
        # Check if worker is processing
        if recent_success.count() == 0 and recent_failures.count() == 0:
            self.stdout.write("\n🚨 WARNING: No recent task execution found!")
            self.stdout.write("   The worker might not be processing tasks.")
        else:
            self.stdout.write("\n✅ Worker appears to be processing tasks.")
        
        self.stdout.write("\n🔧 Recommendations:")
        if overdue_tasks.count() > 0:
            self.stdout.write("  - Update overdue task schedules")
        if pending_tasks.count() > 0:
            self.stdout.write("  - Check if worker is running: python manage.py qcluster")
        if recent_success.count() == 0 and recent_failures.count() == 0:
            self.stdout.write("  - Restart worker: pkill -f qcluster && python manage.py qcluster") 