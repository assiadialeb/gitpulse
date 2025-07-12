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


class DeveloperGroup(Document):
    """MongoDB document for grouping developers with multiple usernames/emails"""
    # Primary identifier
    primary_name = fields.StringField(required=True)
    primary_email = fields.StringField(required=True)
    github_id = fields.StringField()  # GitHub user ID if available
    
    # Application context (None for global groups)
    application_id = fields.IntField(required=False, null=True)
    
    # Group metadata
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    is_auto_grouped = fields.BooleanField(default=True)  # True if auto-detected, False if manual
    
    # Grouping confidence score (0-100)
    confidence_score = fields.IntField(default=0)
    
    # MongoDB settings
    meta = {
        'collection': 'developer_groups',
        'indexes': [
            'application_id',
            'primary_email',
            'github_id',
            ('application_id', 'primary_email'),
            ('application_id', 'github_id'),
        ]
    }
    
    def __str__(self):
        return f"{self.primary_name} ({self.primary_email})"


class DeveloperAlias(Document):
    """MongoDB document for storing developer aliases/identities"""
    # Link to developer group
    group = fields.ReferenceField(DeveloperGroup, required=True)
    
    # Identity information
    name = fields.StringField(required=True)
    email = fields.StringField(required=True)
    
    # Source information
    first_seen = fields.DateTimeField(default=datetime.utcnow)
    last_seen = fields.DateTimeField(default=datetime.utcnow)
    commit_count = fields.IntField(default=0)
    
    # MongoDB settings
    meta = {
        'collection': 'developer_aliases',
        'indexes': [
            'group',
            'email',
            'name',
            ('email', 'name'),
        ]
    }
    
    def __str__(self):
        return f"{self.name} ({self.email})"


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


class RateLimitReset(Document):
    """MongoDB document for tracking rate limit resets and pending task restarts"""
    # User information
    user_id = fields.IntField(required=True)
    github_username = fields.StringField(required=True)
    
    # Rate limit information
    rate_limit_reset_time = fields.DateTimeField(required=True)
    rate_limit_remaining = fields.IntField(default=0)
    rate_limit_limit = fields.IntField(default=5000)
    
    # Pending restart information
    pending_task_type = fields.StringField(choices=['indexing', 'sync', 'background'], required=True)
    pending_task_data = fields.DictField(required=True)  # Task parameters
    original_task_id = fields.StringField(max_length=100)  # Original task ID if applicable
    
    # Status
    status = fields.StringField(choices=['pending', 'scheduled', 'completed', 'failed', 'cancelled'], default='pending')
    
    # Timestamps
    created_at = fields.DateTimeField(required=True, default=datetime.utcnow)
    scheduled_at = fields.DateTimeField()
    completed_at = fields.DateTimeField()
    
    # Error handling
    error_message = fields.StringField()
    retry_count = fields.IntField(default=0)
    max_retries = fields.IntField(default=3)
    
    # MongoDB settings
    meta = {
        'collection': 'rate_limit_resets',
        'indexes': [
            'user_id',
            'rate_limit_reset_time',
            'status',
            'pending_task_type',
            ('user_id', 'status'),
            ('rate_limit_reset_time', 'status'),
        ]
    }
    
    def __str__(self):
        return f"{self.github_username} - {self.pending_task_type} - {self.status}"
    
    @property
    def is_ready_to_restart(self):
        """Check if enough time has passed to restart the task"""
        current_time = datetime.utcnow()
        reset_time = self.rate_limit_reset_time
        return current_time >= reset_time
    
    @property
    def time_until_reset(self):
        """Time until rate limit resets in seconds"""
        if self.is_ready_to_restart:
            return 0
        current_time = datetime.utcnow()
        reset_time = self.rate_limit_reset_time
        return int((reset_time - current_time).total_seconds()) 