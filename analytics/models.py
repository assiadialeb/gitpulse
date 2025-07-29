"""
MongoDB models for analytics data
"""
from datetime import datetime, timezone as dt_timezone
from django.conf import settings
import mongoengine.fields as fields
from mongoengine import Document, EmbeddedDocument
from typing import List, Optional


class IndexingState(Document):
    """MongoDB document for tracking indexing state per repository and entity type"""
    # Repository information
    repository_id = fields.IntField(required=True)  # Repository Django model ID
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    entity_type = fields.StringField(required=True)  # 'deployments', 'pull_requests', 'releases', etc.
    
    # Indexing state
    last_indexed_at = fields.DateTimeField(null=True)  # Last date/time indexed for this entity
    last_run_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))  # When the task was last executed
    status = fields.StringField(choices=['pending', 'running', 'completed', 'error'], default='pending')
    
    # Statistics
    total_indexed = fields.IntField(default=0)  # Total number of items indexed
    batch_size_days = fields.IntField(default=30)  # Days per batch for this entity
    
    # Error handling
    error_message = fields.StringField(null=True)
    retry_count = fields.IntField(default=0)
    max_retries = fields.IntField(default=3)
    
    # Metadata
    created_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    updated_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    # MongoDB settings
    meta = {
        'collection': 'indexing_states',
        'indexes': [
            'repository_id',
            'entity_type',
            'status',
            'last_run_at',
            ('repository_id', 'entity_type'),  # Unique combination
            ('status', 'last_run_at'),
        ]
    }
    
    def __str__(self):
        return f"{self.repository_full_name} - {self.entity_type} - {self.status}"


class FileChange(EmbeddedDocument):
    """Embedded document for file changes in a commit"""
    filename = fields.StringField(required=True)
    additions = fields.IntField(default=0)
    deletions = fields.IntField(default=0)
    changes = fields.IntField(default=0)
    status = fields.StringField(choices=['added', 'modified', 'removed', 'renamed'])
    patch = fields.StringField()  # Optional patch content


class Developer(Document):
    """MongoDB document for grouping developers with multiple usernames/emails"""
    # Primary identifier
    primary_name = fields.StringField(required=True)
    primary_email = fields.StringField(required=True)
    github_id = fields.StringField()  # GitHub user ID if available
    
    # Application context (None for global developers)
    application_id = fields.IntField(required=False, null=True)
    
    # Developer metadata
    created_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    updated_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    is_auto_grouped = fields.BooleanField(default=True)  # True if auto-detected, False if manual
    
    # Grouping confidence score (0-100)
    confidence_score = fields.IntField(default=0)
    
    # MongoDB settings
    meta = {
        'collection': 'developers',
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
    # Link to developer (optional - can be None if not grouped yet)
    developer = fields.ReferenceField(Developer, required=False)
    
    # Identity information
    name = fields.StringField(required=True)
    email = fields.StringField(required=True)
    
    # Source information
    first_seen = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    last_seen = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    commit_count = fields.IntField(default=0)
    
    # MongoDB settings
    meta = {
        'collection': 'developer_aliases',
        'indexes': [
            'developer',
            'email',
            'name',
            ('email', 'name'),
        ]
    }
    
    def __str__(self):
        return f"{self.name} ({self.email})"


class Commit(Document):
    """MongoDB document for storing commit data"""
    # Unique identifier (composite with repository)
    sha = fields.StringField(required=True, max_length=40)
    
    # Repository information
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    application_id = fields.IntField(required=False, null=True)  # Link to Django Application (optional for repository-based indexing)
    
    # Commit metadata
    message = fields.StringField(required=True)
    author_name = fields.StringField(required=True)
    author_email = fields.StringField(required=True)
    committer_name = fields.StringField(required=True)
    committer_email = fields.StringField(required=True)
    
    # Timestamps (timezone-aware)
    authored_date = fields.DateTimeField(required=True)
    committed_date = fields.DateTimeField(required=True)
    
    # Statistics
    additions = fields.IntField(default=0)
    deletions = fields.IntField(default=0)
    total_changes = fields.IntField(default=0)
    files_changed = fields.ListField(fields.EmbeddedDocumentField(FileChange))
    
    # Commit classification
    commit_type = fields.StringField(choices=['fix', 'feature', 'docs', 'refactor', 'test', 'style', 'chore', 'other'], default='other')

    # PR metadata (nouveaux champs)
    pull_request_number = fields.IntField(null=True)
    pull_request_url = fields.StringField(null=True)
    pull_request_merged_at = fields.DateTimeField(null=True)
    
    # Metadata
    parent_shas = fields.ListField(fields.StringField(max_length=40))
    tree_sha = fields.StringField(max_length=40)
    url = fields.URLField()
    
    # Sync tracking
    synced_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    # MongoDB settings
    meta = {
        'collection': 'commits',
        'indexes': [
            'repository_full_name',
            'application_id',
            'author_email',
            'authored_date',
            ('repository_full_name', 'authored_date'),
            ('application_id', 'authored_date'),
            # Composite unique index: SHA + repository (unique constraint)
            ('sha', 'repository_full_name'),
        ]
    }
    
    def get_authored_date_in_timezone(self):
        """Get authored_date converted to the configured timezone"""
        authored_date = getattr(self, 'authored_date', None)
        if authored_date:
            # If naive, assume UTC (since we store everything in UTC)
            if authored_date.tzinfo is None:
                authored_date = authored_date.replace(tzinfo=dt_timezone.utc)
            # Convert to configured timezone
            from django.utils import timezone as django_timezone
            return django_timezone.localtime(authored_date)
        return authored_date
    
    def get_committed_date_in_timezone(self):
        """Get committed_date converted to the configured timezone"""
        committed_date = getattr(self, 'committed_date', None)
        if committed_date:
            # If naive, assume UTC (since we store everything in UTC)
            if committed_date.tzinfo is None:
                committed_date = committed_date.replace(tzinfo=dt_timezone.utc)
            # Convert to configured timezone
            from django.utils import timezone as django_timezone
            return django_timezone.localtime(committed_date)
        return committed_date
    
    def __str__(self):
        sha = getattr(self, 'sha', None)
        message = getattr(self, 'message', None)
        repository_full_name = getattr(self, 'repository_full_name', 'unknown')
        sha_short = sha[:8] if sha else 'unknown'
        message_short = message[:50] if message else 'No message'
        return f"{repository_full_name}:{sha_short} - {message_short}"


class SyncLog(Document):
    """MongoDB document for tracking synchronization logs"""
    # Repository information
    repository_full_name = fields.StringField(required=True)
    application_id = fields.IntField(required=False, null=True)
    
    # Sync metadata
    sync_type = fields.StringField(choices=['full', 'incremental'], required=True)
    status = fields.StringField(choices=['running', 'completed', 'failed'], required=True)
    
    # Timestamps
    started_at = fields.DateTimeField(required=True, default=lambda: datetime.now(dt_timezone.utc))
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
    application_id = fields.IntField(required=False, null=True)
    
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
    created_at = fields.DateTimeField(required=True, default=lambda: datetime.now(dt_timezone.utc))
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
        reset_time = getattr(self, 'rate_limit_reset_time', None)
        if reset_time:
            return current_time >= reset_time
        return False
    
    @property
    def time_until_reset(self):
        """Time until rate limit resets in seconds"""
        if self.is_ready_to_restart:
            return 0
        current_time = datetime.utcnow()
        reset_time = getattr(self, 'rate_limit_reset_time', None)
        if reset_time:
            return int((reset_time - current_time).total_seconds())
        return 0 


class Deployment(Document):
    """MongoDB document for storing GitHub deployments"""
    deployment_id = fields.StringField(required=True)  # Unique per repository, not globally
    application_id = fields.IntField(required=False, null=True)
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    environment = fields.StringField()
    creator = fields.StringField()
    created_at = fields.DateTimeField()
    updated_at = fields.DateTimeField()
    statuses = fields.ListField(fields.DictField())  # List of deployment statuses
    payload = fields.DictField()  # Raw deployment payload (optional)

    meta = {
        'collection': 'deployments',
        'indexes': [
            'deployment_id',
            'application_id',
            'repository_full_name',
            ('application_id', 'repository_full_name'),
            ('deployment_id', 'repository_full_name'),  # Unique constraint per repository
            'environment',
            'created_at',
        ]
    }

    def __str__(self):
        return f"{self.repository_full_name} - {self.environment} - {self.deployment_id}" 


class Release(Document):
    """MongoDB document for storing GitHub releases"""
    release_id = fields.StringField(required=True)  # Unique per repository, not globally
    application_id = fields.IntField(required=False, null=True)
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    tag_name = fields.StringField()
    name = fields.StringField()
    author = fields.StringField()
    published_at = fields.DateTimeField()
    draft = fields.BooleanField(default=False)
    prerelease = fields.BooleanField(default=False)
    body = fields.StringField()
    html_url = fields.StringField()
    assets = fields.ListField(fields.DictField())
    payload = fields.DictField()  # Raw release payload (optionnel)

    meta = {
        'collection': 'releases',
        'indexes': [
            'release_id',
            'application_id',
            'repository_full_name',
            ('application_id', 'repository_full_name'),
            ('release_id', 'repository_full_name'),  # Unique constraint per repository
            'tag_name',
            'published_at',
        ]
    }

    def __str__(self):
        return f"{self.repository_full_name} - {self.tag_name} - {self.release_id}" 


class PullRequest(Document):
    """MongoDB document for storing GitHub Pull Requests"""
    application_id = fields.IntField(required=False, null=True)
    repository_full_name = fields.StringField(required=True)  # e.g., "owner/repo"
    number = fields.IntField(required=True)
    title = fields.StringField()
    author = fields.StringField()
    created_at = fields.DateTimeField()
    updated_at = fields.DateTimeField()
    closed_at = fields.DateTimeField()
    merged_at = fields.DateTimeField()
    state = fields.StringField()  # open/closed
    url = fields.StringField()
    labels = fields.ListField(fields.StringField())
    
    # Nouveaux champs pour les métriques détaillées
    merged_by = fields.StringField()  # Qui a fait le merge
    requested_reviewers = fields.ListField(fields.StringField())  # Reviewers demandés
    assignees = fields.ListField(fields.StringField())  # Assignés
    review_comments_count = fields.IntField(default=0)  # Nombre de commentaires de review
    comments_count = fields.IntField(default=0)  # Nombre total de commentaires
    commits_count = fields.IntField(default=0)  # Nombre de commits
    additions_count = fields.IntField(default=0)  # Lignes ajoutées
    deletions_count = fields.IntField(default=0)  # Lignes supprimées
    changed_files_count = fields.IntField(default=0)  # Nombre de fichiers modifiés
    
    payload = fields.DictField()  # Raw PR payload (optionnel)

    meta = {
        'collection': 'pull_requests',
        'indexes': [
            'application_id',
            'repository_full_name',
            'number',
            'author',
            'state',
            'merged_at',
            'merged_by',
            'url',  # Unique constraint - URL is globally unique
            ('application_id', 'repository_full_name'),
            ('application_id', 'number'),
            ('repository_full_name', 'number'),
            # Index unique pour éviter les doublons
            ('application_id', 'repository_full_name', 'number'),
        ]
    }

    def __str__(self):
        return f"{self.repository_full_name}#{self.number} - {self.title}" 