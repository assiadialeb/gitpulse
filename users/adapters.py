from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialToken, SocialApp
import logging

logger = logging.getLogger(__name__)

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to capture GitHub tokens during OAuth login
    """
    
    def pre_social_login(self, request, sociallogin):
        """
        Capture the access token before the social login is processed
        """
        if sociallogin.account.provider == 'github':
            try:
                # Get the access token from the social login
                access_token = sociallogin.token.token if hasattr(sociallogin, 'token') and sociallogin.token else None
                
                if access_token:
                    logger.info(f"Capturing GitHub token for user {sociallogin.account.user.username}")
                    
                    # Store the token in SocialToken
                    from allauth.socialaccount.models import SocialApp
                    social_app = SocialApp.objects.filter(provider='github').first()
                    if social_app:
                        social_token, created = SocialToken.objects.get_or_create(
                            account=sociallogin.account,
                            app=social_app,
                            defaults={'token': access_token}
                        )
                        
                        if not created:
                            # Update existing token
                            social_token.token = access_token
                            social_token.save()
                        
                        logger.info(f"GitHub token captured and stored for user {sociallogin.account.user.username}")
                        
                        # Also store in session for immediate use
                        request.session['github_token'] = access_token
                    
            except Exception as e:
                logger.error(f"Error capturing GitHub token: {e}")
        
        # Call the parent method
        super().pre_social_login(request, sociallogin) 