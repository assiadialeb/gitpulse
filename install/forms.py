from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from github.models import GitHubApp
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site


class SuperUserCreationForm(UserCreationForm):
    """Form for creating the initial superuser"""
    email = forms.EmailField(required=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_staff = True
        user.is_superuser = True
        if commit:
            user.save()
        return user


class GitHubOAuthForm(forms.ModelForm):
    """Form for GitHub OAuth configuration"""
    oauth_secret = forms.CharField(
        widget=forms.PasswordInput(),
        help_text="Your OAuth App's client secret (NOT a Personal Access Token)"
    )
    
    class Meta:
        model = GitHubApp
        fields = ['client_id']
        labels = {
            'client_id': 'Client ID',
        }
        help_texts = {
            'client_id': 'Your OAuth App\'s client ID',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields required
        self.fields['client_id'].required = True
        self.fields['oauth_secret'].required = True
    
    def save(self, commit=True):
        github_app = super().save(commit=False)
        github_app.client_secret = self.cleaned_data['oauth_secret']
        
        if commit:
            github_app.save()
            
            # Also create/update SocialApp for user SSO
            site = Site.objects.get_current()
            social_app, created = SocialApp.objects.get_or_create(
                provider='github',
                defaults={'name': 'GitHub', 'client_id': github_app.client_id}
            )
            social_app.client_id = github_app.client_id
            social_app.secret = github_app.client_secret
            social_app.save()
            social_app.sites.set([site])
        
        return github_app 