"""
MongoDB models for GitPulse using mongoengine
"""
from mongoengine import Document, StringField, DateTimeField, IntField, ListField, ReferenceField, DictField, BooleanField
from datetime import datetime, timezone
from django.contrib.auth.models import User

class GitHubUser(Document):
    """GitHub user information"""
    github_id = IntField(required=True, unique=True)
    login = StringField(required=True)
    name = StringField()
    email = StringField()
    avatar_url = StringField()
    
    # Additional profile information
    bio = StringField()
    company = StringField()
    blog = StringField()
    location = StringField()
    hireable = BooleanField()
    
    # Statistics
    public_repos = IntField(default=0)
    public_gists = IntField(default=0)
    followers = IntField(default=0)
    following = IntField(default=0)
    
    # Emails list
    emails = ListField(DictField(), default=list)
    
    # Timestamps
    github_created_at = DateTimeField()
    github_updated_at = DateTimeField()
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    
    meta = {'collection': 'github_users'}

class Repository(Document):
    """GitHub repository information"""
    github_id = IntField(required=True, unique=True)
    name = StringField(required=True)
    full_name = StringField(required=True)
    description = StringField()
    private = StringField()
    fork = StringField()
    language = StringField()
    created_at = DateTimeField()
    updated_at = DateTimeField()
    
    meta = {'collection': 'repositories'}

class Commit(Document):
    """Git commit information"""
    sha = StringField(required=True)  # Not unique globally, composite with repository
    repository = ReferenceField(Repository, required=True)
    author = ReferenceField(GitHubUser, required=True)
    committer = ReferenceField(GitHubUser)
    message = StringField(required=True)
    commit_date = DateTimeField(required=True)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    
    # Commit statistics
    additions = IntField(default=0)
    deletions = IntField(default=0)
    total = IntField(default=0)
    
    meta = {
        'collection': 'commits',
        'indexes': [
            ('sha', 'repository'),  # Composite unique index
        ]
    }

class PullRequest(Document):
    """GitHub pull request information"""
    github_id = IntField(required=True, unique=True)
    number = IntField(required=True)
    repository = ReferenceField(Repository, required=True)
    title = StringField(required=True)
    body = StringField()
    state = StringField(required=True)  # open, closed, merged
    author = ReferenceField(GitHubUser, required=True)
    assignees = ListField(ReferenceField(GitHubUser))
    reviewers = ListField(ReferenceField(GitHubUser))
    
    # Timestamps
    created_at = DateTimeField(required=True)
    updated_at = DateTimeField()
    closed_at = DateTimeField()
    merged_at = DateTimeField()
    
    # PR statistics
    additions = IntField(default=0)
    deletions = IntField(default=0)
    changed_files = IntField(default=0)
    commits_count = IntField(default=0)
    
    meta = {'collection': 'pull_requests'}

class UserProfile(Document):
    """Extended user profile with GitHub integration"""
    django_user = StringField(required=True)  # Reference to Django User
    github_user = ReferenceField(GitHubUser)
    github_token = StringField()  # OAuth token (encrypted in production)
    github_token_expires_at = DateTimeField()
    
    # User preferences
    timezone = StringField(default='UTC')
    email_notifications = StringField(default=True)
    
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    
    meta = {'collection': 'user_profiles'} 