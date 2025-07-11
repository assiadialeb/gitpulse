from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class GitHubApp(models.Model):
    """GitHub App configuration for OAuth2"""
    client_id = models.CharField(max_length=100, unique=True)
    client_secret = models.CharField(max_length=100)
    
    # App permissions
    repo_permissions = models.JSONField(default=dict)
    org_permissions = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'GitHub App'
        verbose_name_plural = 'GitHub Apps'
    
    def __str__(self):
        return f"GitHub App (ID: {self.client_id})"


class GitHubInstallation(models.Model):
    """GitHub App installation for a user/organization"""
    installation_id = models.IntegerField(unique=True)
    account_type = models.CharField(max_length=20, choices=[
        ('User', 'User'),
        ('Organization', 'Organization'),
    ])
    account_id = models.IntegerField()
    account_login = models.CharField(max_length=100)
    account_name = models.CharField(max_length=100)
    
    # Installation permissions
    permissions = models.JSONField(default=dict)
    repositories = models.JSONField(default=list)
    
    # Installation status
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspended_by = models.CharField(max_length=100, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'GitHub Installation'
        verbose_name_plural = 'GitHub Installations'
    
    def __str__(self):
        return f"{self.account_login} ({self.account_type})"


class GitHubToken(models.Model):
    """OAuth2 tokens for GitHub API access"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    access_token = models.CharField(max_length=500)
    token_type = models.CharField(max_length=20, default='bearer')
    scope = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    
    # GitHub user info
    github_user_id = models.IntegerField()
    github_username = models.CharField(max_length=100)
    github_email = models.EmailField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'GitHub Token'
        verbose_name_plural = 'GitHub Tokens'
    
    def __str__(self):
        return f"{self.github_username} ({self.user.username})"
    
    @property
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() > self.expires_at
    
    @property
    def expires_in_seconds(self):
        """Time until token expires in seconds"""
        if self.is_expired:
            return 0
        return int((self.expires_at - timezone.now()).total_seconds())


class GitHubOAuthState(models.Model):
    """OAuth2 state parameter for CSRF protection"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    state = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'GitHub OAuth State'
        verbose_name_plural = 'GitHub OAuth States'
    
    def __str__(self):
        return f"{self.user.username} - {self.state}"
    
    @property
    def is_expired(self):
        """State expires after 10 minutes"""
        return timezone.now() > self.created_at + timedelta(minutes=10)
