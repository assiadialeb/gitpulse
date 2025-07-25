from django.db import models
from django.contrib.auth.models import User


class Project(models.Model):
    """
    A project is a simple grouping of repositories.
    All stats are calculated by aggregating repository data.
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    repositories = models.ManyToManyField('repositories.Repository', related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_total_commits(self):
        """Get total commits across all repositories in this project"""
        return sum(repo.commit_count for repo in self.repositories.all())
    
    def get_total_developers(self):
        """Get total unique developers across all repositories in this project"""
        from analytics.models import Developer
        repo_ids = [repo.id for repo in self.repositories.all()]
        return Developer.objects.filter(
            commits__repository_id__in=repo_ids
        ).distinct().count()
    
    def get_total_repositories(self):
        """Get total number of repositories in this project"""
        return self.repositories.count()
