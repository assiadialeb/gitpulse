from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.socialaccount.models import SocialAccount, SocialToken
from allauth.socialaccount.signals import pre_social_login
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

@receiver(pre_social_login)
def capture_github_token(sender, request, sociallogin, **kwargs):
    """
    Capture GitHub token when user connects via OAuth
    """
    if sociallogin.account.provider == 'github':
        try:
            # Get the access token from the social login
            access_token = sociallogin.token.token if hasattr(sociallogin, 'token') and sociallogin.token else None
            
            if access_token:
                # Store the token in SocialToken
                from allauth.socialaccount.models import SocialApp
                social_app = SocialApp.objects.filter(provider='github').first()
                if social_app:
                    try:
                        social_token, created = SocialToken.objects.get_or_create(
                            account=sociallogin.account,
                            app=social_app,
                            defaults={'token': access_token}
                        )
                        
                        if not created:
                            # Update existing token
                            social_token.token = access_token
                            social_token.save()
                        
                        logger.info(f"GitHub token captured for user {sociallogin.account.user.username}")
                        
                        # Also store in session for immediate use
                        request.session['github_token'] = access_token
                    except Exception as e:
                        logger.error(f"Error storing GitHub token: {e}")
                else:
                    logger.warning("GitHub SocialApp not configured, skipping token storage")
                
        except Exception as e:
            logger.error(f"Error capturing GitHub token: {e}")

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create user profile when user is created
    """
    if created:
        from .models import UserProfile
        try:
            UserProfile.objects.get_or_create(user=instance)
        except Exception as e:
            # Log error but don't fail user creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating user profile for {instance.username}: {e}") 