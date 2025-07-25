from django.core.management.base import BaseCommand
from analytics.models import Developer
from pymongo import MongoClient
from django.conf import settings


class Command(BaseCommand):
    help = 'Clean up old fields from Developer documents in MongoDB'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup of Developer documents...')
        
        try:
            # Connect to MongoDB directly
            client = MongoClient(
                host=getattr(settings, 'MONGODB_HOST', 'localhost'),
                port=getattr(settings, 'MONGODB_PORT', 27017)
            )
            db_name = getattr(settings, 'MONGODB_NAME', 'gitpulse')
            db = client[db_name]
            collection = db['developers']
            
            # Fields to remove
            fields_to_remove = [
                'similarity_flags',
                'merge_history', 
                'last_deduplication_check',
                'manual_review_required',
                'deduplication_score'
            ]
            
            # Count documents with old fields
            total_docs = collection.count_documents({})
            docs_with_old_fields = 0
            
            for field in fields_to_remove:
                count = collection.count_documents({field: {'$exists': True}})
                if count > 0:
                    docs_with_old_fields += count
                    self.stdout.write(f'Found {count} documents with field "{field}"')
            
            if docs_with_old_fields == 0:
                self.stdout.write(self.style.SUCCESS('No documents with old fields found. Nothing to clean up.'))
                return
            
            # Remove old fields from all documents
            for field in fields_to_remove:
                result = collection.update_many(
                    {field: {'$exists': True}},
                    {'$unset': {field: 1}}
                )
                if result.modified_count > 0:
                    self.stdout.write(f'Removed field "{field}" from {result.modified_count} documents')
            
            self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {total_docs} Developer documents'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during cleanup: {str(e)}'))
            raise 