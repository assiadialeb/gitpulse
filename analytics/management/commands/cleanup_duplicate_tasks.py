#!/usr/bin/env python3
"""
Django management command to cleanup duplicate intelligent indexing tasks
"""
from django.core.management.base import BaseCommand
from django_q.models import Schedule
from django.db.models import Count
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup duplicate intelligent indexing tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--repository-id',
            type=int,
            help='Cleanup tasks for specific repository ID only',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        repository_id = options.get('repository_id')
        
        self.stdout.write("🔍 Analyzing duplicate intelligent indexing tasks...")
        
        # Task patterns to check for duplicates
        task_patterns = [
            'pullrequest_indexing_repo_',
            'release_indexing_repo_',
            'commit_indexing_repo_',
            'deployment_indexing_repo_',
        ]
        
        total_deleted = 0
        
        for pattern in task_patterns:
            self.stdout.write(f"\n📋 Checking tasks with pattern: {pattern}")
            
            # Get all schedules with this pattern
            schedules = Schedule.objects.filter(name__startswith=pattern)
            
            if repository_id:
                # Filter by specific repository
                schedules = schedules.filter(name__contains=f'repo_{repository_id}')
            
            # Group by name to find duplicates
            duplicates = schedules.values('name').annotate(count=Count('id')).filter(count__gt=1)
            
            for duplicate in duplicates:
                task_name = duplicate['name']
                count = duplicate['count']
                
                self.stdout.write(f"  ⚠️  Found {count} tasks with name: {task_name}")
                
                # Get all tasks with this name, ordered by creation time
                tasks = Schedule.objects.filter(name=task_name).order_by('id')
                
                # Keep the first one, delete the rest
                tasks_to_delete = list(tasks[1:])  # All except the first
                
                if dry_run:
                    self.stdout.write(f"    Would delete {len(tasks_to_delete)} duplicate tasks")
                    for task in tasks_to_delete:
                        self.stdout.write(f"      - ID: {task.id}, Next run: {task.next_run}")
                else:
                    # Delete duplicates
                    deleted_count = len(tasks_to_delete)
                    for task in tasks_to_delete:
                        task.delete()
                    total_deleted += deleted_count
                    self.stdout.write(f"    ✅ Deleted {deleted_count} duplicate tasks")
        
        # Also check for orphaned retry tasks
        self.stdout.write(f"\n🧹 Checking for orphaned retry tasks...")
        
        retry_patterns = [
            'pullrequest_indexing_repo_*_retry',
            'release_indexing_repo_*_retry',
            'deployment_indexing_repo_*_retry',
        ]
        
        for pattern in retry_patterns:
            # Convert pattern to database query
            if pattern == 'pullrequest_indexing_repo_*_retry':
                retry_tasks = Schedule.objects.filter(name__startswith='pullrequest_indexing_repo_').filter(name__endswith='_retry')
            elif pattern == 'release_indexing_repo_*_retry':
                retry_tasks = Schedule.objects.filter(name__startswith='release_indexing_repo_').filter(name__endswith='_retry')
            elif pattern == 'deployment_indexing_repo_*_retry':
                retry_tasks = Schedule.objects.filter(name__startswith='deployment_indexing_repo_').filter(name__endswith='_retry')
            
            if repository_id:
                retry_tasks = retry_tasks.filter(name__contains=f'repo_{repository_id}')
            
            retry_count = retry_tasks.count()
            
            if retry_count > 0:
                self.stdout.write(f"  Found {retry_count} retry tasks for pattern: {pattern}")
                
                if dry_run:
                    for task in retry_tasks:
                        self.stdout.write(f"    - {task.name} (ID: {task.id})")
                else:
                    retry_tasks.delete()
                    self.stdout.write(f"    ✅ Deleted {retry_count} retry tasks")
        
        # Summary
        if dry_run:
            self.stdout.write(f"\n📊 DRY RUN SUMMARY:")
            self.stdout.write(f"  Would delete {total_deleted} duplicate tasks")
            self.stdout.write(f"  Run without --dry-run to actually delete them")
        else:
            self.stdout.write(f"\n✅ CLEANUP COMPLETED:")
            self.stdout.write(f"  Deleted {total_deleted} duplicate tasks")
        
        # Show current task count
        total_tasks = Schedule.objects.count()
        self.stdout.write(f"\n📈 Current total tasks in database: {total_tasks}") 