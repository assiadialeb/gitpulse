from django import forms
from .models import GitHubApp
from allauth.socialaccount.models import SocialApp


class GitHubAppForm(forms.ModelForm):
    """Form for GitHub App configuration"""
    
    class Meta:
        model = GitHubApp
        fields = ['client_id', 'client_secret']
        widgets = {
            'client_id': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'GitHub App Client ID'
            }),
            'client_secret': forms.PasswordInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'GitHub App Client Secret'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default values for hidden fields
        if not self.instance.pk:
            self.instance.repo_permissions = {
                'contents': 'read',
                'metadata': 'read',
            }
            self.instance.org_permissions = {
                'members': 'read',
            }
    
    def save(self, commit=True):
        """Save the form with default values for required fields"""
        instance = super().save(commit=False)
        
        # Set default values if not already set
        if not instance.repo_permissions:
            instance.repo_permissions = {
                'contents': 'read',
                'metadata': 'read',
            }
        if not instance.org_permissions:
            instance.org_permissions = {
                'members': 'read',
            }
        
        if commit:
            instance.save()
        return instance 


class SocialAppForm(forms.ModelForm):
    class Meta:
        model = SocialApp
        fields = ['client_id', 'secret'] 