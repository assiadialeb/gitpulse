from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError


class UserProfile(models.Model):
    """Extended user profile with GitHub integration"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    github_username = models.CharField(max_length=100, blank=True, null=True)
    github_token = models.CharField(max_length=500, blank=True, null=True)
    github_token_expires_at = models.DateTimeField(blank=True, null=True)
    
    # Profile info
    avatar_url = models.URLField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"{self.user.username}'s profile"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    instance.userprofile.save()


class UserDeveloperLink(models.Model):
    """Model to link users with developers"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='developer_link')
    developer_id = models.CharField(max_length=24, help_text="MongoDB ObjectId of the developer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Developer Link"
        verbose_name_plural = "User Developer Links"
        unique_together = ['user', 'developer_id']

    def clean(self):
        """Validate that user and developer are not already linked elsewhere"""
        if self.pk:  # If updating existing instance
            return
        
        # Check if user is already linked
        if UserDeveloperLink.objects.filter(user=self.user).exists():
            raise ValidationError("This user is already linked to a developer.")
        
        # Check if developer is already linked
        if UserDeveloperLink.objects.filter(developer_id=self.developer_id).exists():
            raise ValidationError("This developer is already linked to a user.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} -> Developer {self.developer_id}"
