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
    

