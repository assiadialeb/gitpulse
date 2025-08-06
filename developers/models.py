from django.db import models
from django.contrib.auth.models import User
import uuid


class Developer(models.Model):
    """A developer with multiple aliases that represent the same person"""
    id = models.CharField(primary_key=True, max_length=24)  # MongoDB ObjectId length
    name = models.CharField(max_length=255)
    email = models.EmailField()
    
    # GitHub Teams integration
    github_teams = models.JSONField(default=list, blank=True, help_text="List of GitHub team slugs")
    github_organizations = models.JSONField(default=list, blank=True, help_text="List of GitHub organization names")
    primary_team = models.CharField(max_length=100, blank=True, help_text="Main team for this developer")
    team_role = models.CharField(max_length=50, blank=True, help_text="Role in the team (member, admin, etc.)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'developers'
        indexes = [
            models.Index(fields=['name', 'email']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.email})"
    
    def get_total_commits(self):
        """Total commits across all aliases for this developer"""
        total = 0
        for alias in self.aliases.all():
            total += alias.commit_count
        return total


class DeveloperAlias(models.Model):
    """Individual developer alias (name/email combination)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    developer = models.ForeignKey(Developer, on_delete=models.CASCADE, related_name='aliases', null=True, blank=True)
    commit_count = models.IntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'developer_aliases'
        indexes = [
            models.Index(fields=['name', 'email']),
            models.Index(fields=['developer']),
        ]
        unique_together = ['name', 'email']
    
    def __str__(self):
        return f"{self.name} ({self.email})"
    
    @property
    def display_name(self):
        """Display name - either developer name or individual name"""
        if self.developer:
            return self.developer.name
        return self.name
