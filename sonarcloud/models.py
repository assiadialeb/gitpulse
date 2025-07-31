from django.db import models


class SonarCloudConfig(models.Model):
    """SonarCloud configuration"""
    access_token = models.CharField(max_length=500, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'SonarCloud Configuration'
        verbose_name_plural = 'SonarCloud Configurations'
    
    def __str__(self):
        return f"SonarCloud Config (Updated: {self.updated_at})"
    
    @classmethod
    def get_config(cls):
        """Get the first (and only) configuration instance"""
        config, created = cls.objects.get_or_create(pk=1)
        return config 