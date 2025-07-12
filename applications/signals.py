"""
Signals for applications app
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Application, ApplicationRepository


@receiver(post_delete, sender=Application)
def cleanup_application_mongodb_data(sender, instance, **kwargs):
    """
    Clean up MongoDB data when an application is deleted
    """
    try:
        from analytics.services import cleanup_application_data
        cleanup_results = cleanup_application_data(instance.id)
        
        # Log the cleanup results
        print(f"Cleaned up MongoDB data for application {instance.id}: {cleanup_results}")
        
    except ImportError:
        # Analytics app not available, skip cleanup
        print(f"Analytics app not available, skipping MongoDB cleanup for application {instance.id}")
    except Exception as e:
        # Log error but don't prevent application deletion
        print(f"Error cleaning up MongoDB data for application {instance.id}: {e}")


@receiver(post_delete, sender=ApplicationRepository)
def cleanup_repository_mongodb_data(sender, instance, **kwargs):
    """
    Clean up MongoDB data when a repository is deleted
    """
    try:
        from analytics.services import cleanup_repository_data
        cleanup_results = cleanup_repository_data(instance.github_repo_name)
        
        # Log the cleanup results
        print(f"Cleaned up MongoDB data for repository {instance.github_repo_name}: {cleanup_results}")
        
    except ImportError:
        # Analytics app not available, skip cleanup
        print(f"Analytics app not available, skipping MongoDB cleanup for repository {instance.github_repo_name}")
    except Exception as e:
        # Log error but don't prevent repository deletion
        print(f"Error cleaning up MongoDB data for repository {instance.github_repo_name}: {e}") 