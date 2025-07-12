from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


class Application(models.Model):
    """Application model for grouping multiple GitHub repositories"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(max_length=500)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('applications:detail', kwargs={'pk': self.pk})
    
    @property
    def repository_count(self):
        return self.repositories.count()


class ApplicationRepository(models.Model):
    """Model for linking GitHub repositories to applications"""
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='repositories')
    github_repo_name = models.CharField(max_length=200)  # Format: owner/repo
    github_repo_url = models.URLField(max_length=500, null=True, blank=True)  # Git repository URL (HTTPS or SSH)
    github_repo_id = models.BigIntegerField()  # GitHub repo ID
    description = models.TextField(blank=True, null=True)  # From GitHub
    default_branch = models.CharField(max_length=100, default='main')
    is_private = models.BooleanField(default=False)
    language = models.CharField(max_length=50, blank=True, null=True)  # Primary language
    stars_count = models.IntegerField(default=0)
    forks_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(null=True, blank=True)  # Last push date from GitHub
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['application', 'github_repo_name']
        ordering = ['github_repo_name']
        verbose_name = 'Application Repository'
        verbose_name_plural = 'Application Repositories'
    
    def __str__(self):
        return f"{self.application.name} - {self.github_repo_name}"
    
    @property
    def repo_owner(self):
        """Extract owner from github_repo_name"""
        return self.github_repo_name.split('/')[0] if '/' in self.github_repo_name else ''
    
    @property
    def repo_name(self):
        """Extract repo name from github_repo_name"""
        return self.github_repo_name.split('/')[1] if '/' in self.github_repo_name else self.github_repo_name
