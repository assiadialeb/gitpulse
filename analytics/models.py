"""
MongoDB models for analytics data
"""
from datetime import datetime
from mongoengine import Document, EmbeddedDocument, fields
from typing import List, Optional


class FileChange(EmbeddedDocument):
    """Embedded document for file changes in a commit"""
    filename = fields.StringField(required=True)
    additions = fields.IntField(default=0)
    deletions = fields.IntField(default=0)
    changes = fields.IntField(default=0)
    status = fields.StringField(choices=['added', 'modified', 'removed', 'renamed'])
    patch = fields.StringField()  # Optional patch content


class Commit(Document):
    """MongoDB document for storing commit data"""
    # Unique identifier
    sha = fields.StringField(required=True, unique=True, max_length=40)
    
    # Repository information
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    application_id = fields.IntField(required=True)  # Link to Django Application
    
    # Commit metadata
    message = fields.StringField(required=True)
    author_name = fields.StringField(required=True)
    author_email = fields.StringField(required=True)
    committer_name = fields.StringField(required=True)
    committer_email = fields.StringField(required=True)
    
    # Timestamps
    authored_date = fields.DateTimeField(required=True)
    committed_date = fields.DateTimeField(required=True)
    
    # Statistics
    additions = fields.IntField(default=0)
    deletions = fields.IntField(default=0)
    total_changes = fields.IntField(default=0)
    files_changed = fields.ListField(fields.EmbeddedDocumentField(FileChange))
    
    # Metadata
    parent_shas = fields.ListField(fields.StringField(max_length=40))
    tree_sha = fields.StringField(max_length=40)
    url = fields.URLField()
    
    # Sync tracking
    synced_at = fields.DateTimeField(default=datetime.utcnow)
    
    # MongoDB settings
    meta = {
        'collection': 'commits',
        'indexes': [
            'sha',
            'repository_full_name',
            'application_id',
            'author_email',
            'authored_date',
            ('repository_full_name', 'authored_date'),
            ('application_id', 'authored_date'),
        ]
    }
    
    def __str__(self):
        sha_short = self.sha[:8] if self.sha else 'unknown'
        message_short = self.message[:50] if self.message else 'No message'
        return f"{self.repository_full_name}:{sha_short} - {message_short}"


class SyncLog(Document):
    """MongoDB document for tracking synchronization logs"""
    # Repository information
    repository_full_name = fields.StringField(required=True)
    application_id = fields.IntField(required=True)
    
    # Sync metadata
    sync_type = fields.StringField(choices=['full', 'incremental'], required=True)
    status = fields.StringField(choices=['running', 'completed', 'failed'], required=True)
    
    # Timestamps
    started_at = fields.DateTimeField(required=True, default=datetime.utcnow)
    completed_at = fields.DateTimeField()
    
    # Results
    commits_processed = fields.IntField(default=0)
    commits_new = fields.IntField(default=0)
    commits_updated = fields.IntField(default=0)
    commits_skipped = fields.IntField(default=0)
    
    # Error handling
    error_message = fields.StringField()
    error_details = fields.DictField()
    retry_count = fields.IntField(default=0)
    
    # API usage tracking
    github_api_calls = fields.IntField(default=0)
    rate_limit_remaining = fields.IntField()
    
    # Range processed
    last_commit_date = fields.DateTimeField()
    oldest_commit_date = fields.DateTimeField()
    
    # MongoDB settings
    meta = {
        'collection': 'sync_logs',
        'indexes': [
            'repository_full_name',
            'application_id',
            'status',
            'started_at',
            ('repository_full_name', 'started_at'),
        ]
    }
    
    def __str__(self):
        return f"{self.repository_full_name} - {self.sync_type} sync - {self.status}"


class RepositoryStats(Document):
    """MongoDB document for caching repository statistics"""
    # Repository information
    repository_full_name = fields.StringField(required=True, unique=True)
    application_id = fields.IntField(required=True)
    
    # Last sync info
    last_sync_at = fields.DateTimeField()
    last_commit_sha = fields.StringField(max_length=40)
    last_commit_date = fields.DateTimeField()
    
    # Cached statistics
    total_commits = fields.IntField(default=0)
    total_authors = fields.IntField(default=0)
    total_additions = fields.IntField(default=0)
    total_deletions = fields.IntField(default=0)
    
    # Date ranges
    first_commit_date = fields.DateTimeField()
    
    # Sync configuration
    sync_enabled = fields.BooleanField(default=True)
    sync_frequency_hours = fields.IntField(default=24)  # Sync every 24 hours
    
    # MongoDB settings
    meta = {
        'collection': 'repository_stats',
        'indexes': [
            'repository_full_name',
            'application_id',
            'last_sync_at',
        ]
    }
    
    def __str__(self):
        return f"{self.repository_full_name} - {self.total_commits} commits" 