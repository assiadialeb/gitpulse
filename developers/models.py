from django.db import models
from django.contrib.auth.models import User
import uuid


class DeveloperGroup(models.Model):
    """A group of developer identities that represent the same person"""
    id = models.CharField(primary_key=True, max_length=24)  # MongoDB ObjectId length
    name = models.CharField(max_length=255)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'developer_groups'
        indexes = [
            models.Index(fields=['name', 'email']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.email})"
    
    def get_total_commits(self):
        """Total commits across all identities in this group"""
        total = 0
        for identity in self.identities.all():
            total += identity.commit_count
        return total


class DeveloperIdentity(models.Model):
    """Individual developer identity (name/email combination)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    group = models.ForeignKey(DeveloperGroup, on_delete=models.CASCADE, related_name='identities', null=True, blank=True)
    commit_count = models.IntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'developer_identities'
        indexes = [
            models.Index(fields=['name', 'email']),
            models.Index(fields=['group']),
        ]
        unique_together = ['name', 'email']
    
    def __str__(self):
        return f"{self.name} ({self.email})"
    
    @property
    def display_name(self):
        """Display name - either group name or individual name"""
        if self.group:
            return self.group.name
        return self.name
