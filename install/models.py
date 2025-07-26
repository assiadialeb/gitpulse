from django.db import models
from django.contrib.auth.models import User


class InstallationStep(models.Model):
    """Track installation progress"""
    STEP_CHOICES = [
        ('superuser', 'SuperUser Creation'),
        ('github_oauth', 'GitHub OAuth Configuration'),
        ('schedules', 'Task Schedules'),
    ]
    
    step = models.CharField(max_length=20, choices=STEP_CHOICES, unique=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Installation Step'
        verbose_name_plural = 'Installation Steps'
    
    def __str__(self):
        return f"{self.get_step_display()} - {'Completed' if self.completed else 'Pending'}"


class InstallationLog(models.Model):
    """Log installation events"""
    timestamp = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=[
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('SUCCESS', 'Success'),
    ])
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Installation Log'
        verbose_name_plural = 'Installation Logs'
    
    def __str__(self):
        return f"{self.timestamp} - {self.level}: {self.message}"
