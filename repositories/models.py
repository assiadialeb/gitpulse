from django.db import models
from django.contrib.auth.models import User


class Repository(models.Model):
    """Repository model for storing indexed repositories"""
    
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255, unique=True)  # owner/repo-name
    description = models.TextField(blank=True, null=True)
    private = models.BooleanField(default=False)
    fork = models.BooleanField(default=False)
    language = models.CharField(max_length=50, blank=True, null=True)
    stars = models.IntegerField(default=0)
    forks = models.IntegerField(default=0)
    size = models.BigIntegerField(default=0)
    default_branch = models.CharField(max_length=100, default='main')
    
    # GitHub metadata
    github_id = models.BigIntegerField(unique=True)
    html_url = models.URLField()
    clone_url = models.URLField()
    ssh_url = models.URLField()
    
    # Indexing status
    is_indexed = models.BooleanField(default=False)
    last_indexed = models.DateTimeField(null=True, blank=True)
    commit_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Owner
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='repositories')
    
    class Meta:
        verbose_name_plural = "Repositories"
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.full_name
    
    @property
    def owner_name(self):
        """Extract owner name from full_name"""
        return self.full_name.split('/')[0] if '/' in self.full_name else ''
    
    @property
    def repo_name(self):
        """Extract repository name from full_name"""
        return self.full_name.split('/')[1] if '/' in self.full_name else self.name
