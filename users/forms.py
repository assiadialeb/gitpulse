from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import UserProfile


class CustomUserCreationForm(UserCreationForm):
    """Custom user registration form"""
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'input input-bordered w-full',
        'placeholder': 'Email'
    }))
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'input input-bordered w-full',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={
        'class': 'input input-bordered w-full',
        'placeholder': 'Last Name'
    }))
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'input input-bordered w-full',
            'placeholder': 'Username'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'input input-bordered w-full',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'input input-bordered w-full',
            'placeholder': 'Confirm Password'
        })


class CustomAuthenticationForm(AuthenticationForm):
    """Custom login form"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'input input-bordered w-full',
            'placeholder': 'Username or email'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'input input-bordered w-full',
            'placeholder': 'Password'
        })


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile"""
    class Meta:
        model = UserProfile
        fields = ['github_username']
        widgets = {
            'github_username': forms.TextInput(attrs={
                'class': 'input input-bordered w-full rounded-xl border-gray-200 focus:border-primary-green focus:ring-2 focus:ring-primary-green/20 transition-all duration-300',
                'placeholder': 'Your GitHub username for synchronization'
            })
        } 