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
    
    # GitHub Teams integration
    github_teams = fields.ListField(fields.StringField(), default=list)  # List of team slugs
    github_organizations = fields.ListField(fields.StringField(), default=list)  # List of org names
    primary_team = fields.StringField()  # Main team for this developer
    team_role = fields.StringField()  # Role in the team (member, admin, etc.)
    
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
        ],
        'unique_indexes': [
            'primary_email',  # Contrainte unique sur email
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
        ],
        'unique_indexes': [
            'email',  # Contrainte unique sur email
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
        current_time = datetime.now(dt_timezone.utc)
        reset_time = getattr(self, 'rate_limit_reset_time', None)
        if reset_time:
            return current_time >= reset_time
        return False
    
    @property
    def time_until_reset(self):
        """Time until rate limit resets in seconds"""
        if self.is_ready_to_restart:
            return 0
        current_time = datetime.now(dt_timezone.utc)
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


class SBOM(Document):
    """MongoDB document for storing SBOM data"""
    # Repository information
    repository_full_name = fields.StringField(required=True)
    application_id = fields.IntField(required=False, null=True)
    
    # SBOM metadata
    bom_format = fields.StringField(required=True)  # "CycloneDX"
    spec_version = fields.StringField(required=True)  # "1.6"
    serial_number = fields.StringField(required=True)  # UUID
    version = fields.IntField(required=True)
    
    # Generation metadata
    generated_at = fields.DateTimeField(required=True)
    tool_name = fields.StringField(required=True)  # "cdxgen"
    tool_version = fields.StringField(required=True)  # "11.4.4"
    
    # Component information
    component_count = fields.IntField(default=0)
    vulnerability_count = fields.IntField(default=0)
    
    # Raw data
    raw_sbom = fields.DictField(required=True)  # Complete SBOM JSON
    
    # Metadata
    created_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    updated_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    meta = {
        'collection': 'sboms',
        'indexes': [
            'repository_full_name',
            'application_id',
            'generated_at',
            ('repository_full_name', 'generated_at'),
        ]
    }
    
    def __str__(self):
        return f"SBOM for {self.repository_full_name} ({self.generated_at})"


class SBOMComponent(Document):
    """MongoDB document for storing SBOM components"""
    # Link to SBOM
    sbom_id = fields.ReferenceField(SBOM, required=True)
    
    # Component identification
    group = fields.StringField(required=False)  # e.g., "@cyclonedx"
    name = fields.StringField(required=True)  # e.g., "cdxgen"
    version = fields.StringField(required=True)  # e.g., "11.4.4"
    purl = fields.StringField(required=True)  # Package URL
    bom_ref = fields.StringField(required=True)  # Internal reference
    
    # Component type
    component_type = fields.StringField(required=True)  # "library", "application", etc.
    scope = fields.StringField(default="required")  # "required", "optional", "excluded"
    
    # Licenses
    licenses = fields.ListField(fields.DictField())  # License information
    
    # Hashes
    hashes = fields.ListField(fields.DictField())  # SHA hashes
    
    # Properties
    properties = fields.ListField(fields.DictField())  # Additional properties
    
    # Evidence
    evidence = fields.DictField()  # Evidence of component detection
    
    # Tags
    tags = fields.ListField(fields.StringField())
    
    # Metadata
    created_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    meta = {
        'collection': 'sbom_components',
        'indexes': [
            'sbom_id',
            'name',
            'version',
            'purl',
            ('name', 'version'),
        ]
    }
    
    def __str__(self):
        return f"{self.name}@{self.version}"


class SBOMVulnerability(Document):
    """MongoDB document for storing SBOM vulnerabilities"""
    # Link to SBOM
    sbom_id = fields.ReferenceField(SBOM, required=True)
    
    # Vulnerability identification
    vuln_id = fields.StringField(required=True)  # CVE ID or other identifier
    source_name = fields.StringField(required=True)  # "ossindex", "nvd", etc.
    
    # Vulnerability details
    title = fields.StringField()
    description = fields.StringField()
    severity = fields.StringField(choices=['critical', 'high', 'medium', 'low', 'info'])
    cvss_score = fields.FloatField()
    cvss_vector = fields.StringField()
    
    # Affected component
    affected_component_purl = fields.StringField(required=True)
    affected_component_name = fields.StringField(required=True)
    affected_component_version = fields.StringField(required=True)
    
    # References
    references = fields.ListField(fields.DictField())
    
    # Ratings
    ratings = fields.ListField(fields.DictField())
    
    # Metadata
    published_date = fields.DateTimeField()
    updated_date = fields.DateTimeField()
    
    # Raw data
    raw_vulnerability = fields.DictField(required=True)
    
    # Metadata
    created_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    meta = {
        'collection': 'sbom_vulnerabilities',
        'indexes': [
            'sbom_id',
            'vuln_id',
            'severity',
            'affected_component_purl',
            ('sbom_id', 'severity'),
        ]
    }
    
    def __str__(self):
        return f"{self.vuln_id} - {self.affected_component_name}@{self.affected_component_version}" 


class SonarCloudMetrics(Document):
    """SonarCloud quality metrics for repositories"""
    
    # Repository reference
    repository_id = fields.IntField(required=True)
    repository_full_name = fields.StringField(required=True)
    
    # Timestamp
    timestamp = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    # Quality Gate
    quality_gate = fields.StringField(choices=['PASS', 'FAIL'], default='FAIL')
    
    # Ratings (A, B, C, D, E)
    maintainability_rating = fields.StringField(choices=['A', 'B', 'C', 'D', 'E'])
    reliability_rating = fields.StringField(choices=['A', 'B', 'C', 'D', 'E'])
    security_rating = fields.StringField(choices=['A', 'B', 'C', 'D', 'E'])
    
    # Quantitative metrics
    bugs = fields.IntField(default=0)
    vulnerabilities = fields.IntField(default=0)
    code_smells = fields.IntField(default=0)
    duplicated_lines_density = fields.FloatField(default=0.0)  # %
    coverage = fields.FloatField()  # %
    technical_debt = fields.FloatField()  # hours
    
    # Issues by severity
    issues_blocker = fields.IntField(default=0)
    issues_critical = fields.IntField(default=0)
    issues_major = fields.IntField(default=0)
    issues_minor = fields.IntField(default=0)
    issues_info = fields.IntField(default=0)
    
    # SonarCloud metadata
    sonarcloud_project_key = fields.StringField(required=True)
    sonarcloud_organization = fields.StringField(required=True)
    last_analysis_date = fields.DateTimeField()
    
    # Indexes for efficient queries
    meta = {
        'indexes': [
            ('repository_id', '-timestamp'),
            ('repository_full_name', '-timestamp'),
            ('timestamp',),
            ('quality_gate',),
            ('sonarcloud_project_key',),
        ],
        'collection': 'sonarcloud_metrics'
    }
    
    def total_issues(self):
        """Calculate total open issues"""
        return (self.issues_blocker + self.issues_critical + 
                self.issues_major + self.issues_minor + self.issues_info)
    
    def get_rating_color(self, rating):
        """Get color for rating display"""
        colors = {
            'A': 'green',
            'B': 'blue', 
            'C': 'yellow',
            'D': 'orange',
            'E': 'red'
        }
        return colors.get(rating, 'gray')
    
    def __str__(self):
        return f"SonarCloud Metrics for {self.repository_full_name} at {self.timestamp}"


class CodeQLVulnerability(Document):
    """MongoDB document for storing CodeQL security vulnerabilities"""
    # Repository information
    repository_full_name = fields.StringField(required=True, max_length=255)
    application_id = fields.IntField(null=True)  # For compatibility with existing structure
    
    # Vulnerability identification
    vulnerability_id = fields.StringField(required=True, max_length=255)  # GitHub Alert ID
    rule_id = fields.StringField(required=True, max_length=100)  # CWE-XXX or rule identifier
    rule_description = fields.StringField(max_length=500)
    rule_name = fields.StringField(max_length=255)
    
    # Severity and confidence
    severity = fields.StringField(choices=['critical', 'high', 'medium', 'low'], required=True)
    confidence = fields.StringField(choices=['high', 'medium', 'low'], default='medium')
    
    # State management
    state = fields.StringField(choices=['open', 'dismissed', 'fixed'], default='open')
    dismissed_reason = fields.StringField(choices=['false_positive', 'wont_fix', 'used_in_tests'], null=True)
    dismissed_comment = fields.StringField(max_length=1000, null=True)
    
    # Location information
    file_path = fields.StringField(max_length=500)
    start_line = fields.IntField(null=True)
    end_line = fields.IntField(null=True)
    start_column = fields.IntField(null=True)
    end_column = fields.IntField(null=True)
    
    # Message and description
    message = fields.StringField(max_length=1000)
    description = fields.StringField(max_length=2000)
    
    # Security classification
    category = fields.StringField(max_length=100)  # e.g., "sql-injection", "xss", "path-traversal"
    cwe_id = fields.StringField(max_length=20)  # e.g., "CWE-89"
    
    # Temporal information
    created_at = fields.DateTimeField(required=True)
    updated_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    dismissed_at = fields.DateTimeField(null=True)
    fixed_at = fields.DateTimeField(null=True)
    
    # GitHub metadata
    html_url = fields.URLField(max_length=500)
    number = fields.IntField()  # GitHub alert number
    
    # Analysis metadata
    tool_name = fields.StringField(default='CodeQL')
    tool_version = fields.StringField(max_length=50)
    analyzed_at = fields.DateTimeField(default=lambda: datetime.now(dt_timezone.utc))
    
    # Raw GitHub payload
    payload = fields.DictField()
    
    # MongoDB settings
    meta = {
        'collection': 'codeql_vulnerabilities',
        'indexes': [
            'repository_full_name',
            'vulnerability_id',
            'severity',
            'state',
            'category',
            'created_at',
            ('repository_full_name', 'state'),
            ('repository_full_name', 'severity'),
            ('repository_full_name', 'created_at'),
            ('repository_full_name', 'category'),
            ('vulnerability_id', 'repository_full_name'),  # Unique combination
        ]
    }
    
    def __str__(self):
        return f"CodeQL {self.severity} vulnerability in {self.repository_full_name}: {self.rule_id}"
    
    def is_critical_or_high(self):
        """Check if vulnerability is critical or high severity"""
        return self.severity in ['critical', 'high']
    
    def get_severity_color(self):
        """Get color for severity display"""
        colors = {
            'critical': 'red',
            'high': 'orange',
            'medium': 'yellow',
            'low': 'blue'
        }
        return colors.get(self.severity, 'gray')
    
    def get_age_days(self):
        """Get age of vulnerability in days"""
        if not self.created_at:
            return 0
        now = datetime.now(dt_timezone.utc)
        if self.created_at.tzinfo is None:
            created_at = self.created_at.replace(tzinfo=dt_timezone.utc)
        else:
            created_at = self.created_at
        return (now - created_at).days
    
    def is_recently_fixed(self, days=7):
        """Check if vulnerability was fixed recently"""
        if not self.fixed_at:
            return False
        now = datetime.now(dt_timezone.utc)
        if self.fixed_at.tzinfo is None:
            fixed_at = self.fixed_at.replace(tzinfo=dt_timezone.utc)
        else:
            fixed_at = self.fixed_at
        return (now - fixed_at).days <= days


class RepositoryKLOCHistory(Document):
    """MongoDB document for storing KLOC history per repository"""
    
    # Repository information
    repository_full_name = fields.StringField(required=True, max_length=255)
    repository_id = fields.IntField(required=True)
    
    # KLOC data
    kloc = fields.FloatField(required=True)  # Kilo Lines of Code
    total_lines = fields.IntField(required=True)  # Total lines of code
    language_breakdown = fields.DictField(default={})  # {'Python': 1500, 'JavaScript': 800}
    
    # Calculation metadata
    calculated_at = fields.DateTimeField(required=True, default=lambda: datetime.now(dt_timezone.utc))
    calculation_duration = fields.FloatField(default=0.0)  # Duration in seconds
    
    # File statistics
    total_files = fields.IntField(default=0)
    code_files = fields.IntField(default=0)
    
    # Error handling
    calculation_error = fields.StringField(null=True)
    calculation_success = fields.BooleanField(default=True)
    
    # MongoDB settings
    meta = {
        'collection': 'repository_kloc_history',
        'indexes': [
            'repository_full_name',
            'repository_id',
            'calculated_at',
            'kloc',
            ('repository_full_name', 'calculated_at'),
            ('repository_id', 'calculated_at'),
        ]
    }
    
    def __str__(self):
        return f"KLOC History for {self.repository_full_name}: {self.kloc:.2f} KLOC at {self.calculated_at}"
    
    @property
    def kloc_formatted(self):
        """Get formatted KLOC value"""
        if self.kloc >= 1000:
            return f"{self.kloc/1000:.1f} MLOC"
        else:
            return f"{self.kloc:.1f} KLOC"
    
    @property
    def top_languages(self):
        """Get top 3 languages by line count"""
        if not self.language_breakdown:
            return []
        
        sorted_languages = sorted(
            self.language_breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_languages[:3]


class SecurityHealthHistory(Document):
    """Historical Security Health Score data"""
    
    repository_full_name = fields.StringField(required=True)
    repository_id = fields.IntField(required=True)
    shs_score = fields.FloatField(required=True)  # 0-100
    delta_shs = fields.FloatField(default=0.0)  # Change from previous analysis
    calculated_at = fields.DateTimeField(required=True)
    month = fields.StringField(required=True)  # YYYY-MM format for easy querying
    
    # Metadata
    total_vulnerabilities = fields.IntField(default=0)
    critical_count = fields.IntField(default=0)
    high_count = fields.IntField(default=0)
    medium_count = fields.IntField(default=0)
    low_count = fields.IntField(default=0)
    kloc = fields.FloatField(default=0.0)
    
    meta = {
        'collection': 'security_health_history',
        'indexes': [
            'repository_full_name',
            'repository_id',
            'calculated_at',
            'month'
        ]
    }
    
    def __str__(self):
        return f"SHS {self.repository_full_name}: {self.shs_score:.1f}/100 ({self.calculated_at})"