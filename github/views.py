import os
import secrets
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp, SocialAccount
from .forms import SocialAppForm


@login_required
def admin_view(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied. Superuser required.')
        return redirect('users:dashboard')

    site = Site.objects.get_current()
    social_app = SocialApp.objects.filter(provider='github', sites=site).first()
    if not social_app:
        social_app = SocialApp.objects.create(provider='github', name='GitHub')
        social_app.sites.set([site])
    if request.method == 'POST':
        form = SocialAppForm(request.POST, instance=social_app)
        if form.is_valid():
            social_app = form.save()
            social_app.sites.set([site])
            social_app.save()
            messages.success(request, 'GitHub OAuth configuration saved successfully!')
            return redirect('github:admin')
    else:
        form = SocialAppForm(instance=social_app)

    github_account = SocialAccount.objects.filter(user=request.user, provider='github').first() if request.user.is_authenticated else None
    context = {
        'form': form,
        'redirect_url': request.build_absolute_uri('/accounts/github/login/callback/'),
        'github_connected': github_account is not None,
        'github_username': github_account.extra_data.get('login') if github_account else None,
    }
    return render(request, 'github/admin.html', context)
