from django.db import models


class OSSIndexConfig(models.Model):
    """OSS Index configuration for vulnerability scanning"""
    api_token = models.CharField(max_length=500, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'OSS Index Configuration'
        verbose_name_plural = 'OSS Index Configurations'
    
    def __str__(self):
        return f"OSS Index Config (Updated: {self.updated_at})"
    
    @classmethod
    def get_config(cls):
        """Get the first (and only) configuration instance"""
        config, created = cls.objects.get_or_create(pk=1)
        return config 