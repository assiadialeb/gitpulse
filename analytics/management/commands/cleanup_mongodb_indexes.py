"""
Management command to cleanup conflicting MongoDB indexes
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup conflicting MongoDB indexes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually doing it',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Get MongoDB connection
        mongo_uri = getattr(settings, 'MONGODB_URI', 'mongodb://localhost:27017/gitpulse')
        client = MongoClient(mongo_uri)
        db = client.get_default_database()
        
        self.stdout.write(
            self.style.SUCCESS(
                "🧹 MongoDB Index Cleanup - Removing conflicting indexes"
            )
        )
        
        # List all collections and their indexes
        collections = ['commits', 'indexing_states', 'sync_logs', 'repository_stats', 
                      'rate_limit_resets', 'deployments', 'releases', 'pull_requests',
                      'developers', 'developer_aliases']
        
        for collection_name in collections:
            if collection_name not in db.list_collection_names():
                continue
                
            collection = db[collection_name]
            indexes = list(collection.list_indexes())
            
            self.stdout.write(f"\n📊 Collection: {collection_name}")
            self.stdout.write(f"  Current indexes: {len(indexes)}")
            
            for index in indexes:
                index_name = index['name']
                index_keys = index['key']
                is_unique = index.get('unique', False)
                
                self.stdout.write(f"    - {index_name}: {index_keys} (unique: {is_unique})")
                
                # Check for conflicting indexes in commits collection
                if collection_name == 'commits':
                    if index_name == 'sha_1' and is_unique:
                        # This is the conflicting unique index - remove it (we want composite unique instead)
                        if not dry_run:
                            try:
                                collection.drop_index(index_name)
                                self.stdout.write(
                                    self.style.SUCCESS(f"    ✅ Removed conflicting unique index: {index_name}")
                                )
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(f"    ❌ Failed to remove index {index_name}: {e}")
                                )
                        else:
                            self.stdout.write(
                                self.style.WARNING(f"    🔄 Would remove conflicting unique index: {index_name}")
                            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\n📋 This was a dry run - no indexes were actually removed"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\n🎉 MongoDB index cleanup completed!"
                )
            )
        
        client.close() 