from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.models import User
from .forms import CustomUserCreationForm, CustomAuthenticationForm, UserProfileForm
from .models import UserProfile
from .services import GitHubUserService
# from models import GitHubUser  # Supprimé car inutilisé et cause une erreur linter
from analytics.models import Commit, PullRequest, DeveloperAlias, Developer, Release  # mongoengine
import applications.models  # pour accès Django ORM
from django.utils import timezone
from collections import defaultdict
from allauth.socialaccount.models import SocialAccount, SocialToken
from analytics.analytics_service import AnalyticsService
from analytics.models import Developer as MongoDeveloper, DeveloperAlias as MongoDeveloperAlias
import requests
from models import Repository
from repositories.models import Repository


def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome, {user.username}!')
                return redirect('users:dashboard')
            else:
                # Add error to form instead of using messages
                form.add_error(None, 'Invalid username or password.')
        # Remove the else block that was adding messages.error
    else:
        form = CustomAuthenticationForm()
    
    return render(request, 'users/login.html', {'form': form})


def register_view(request):
    """Registration view"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {user.username}!')
            return redirect('users:dashboard')
        # Remove the else block that was adding messages.error
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'users/register.html', {'form': form})


@login_required
def logout_view(request):
    """Logout view"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('users:login')


@login_required
def profile_view(request):
    """User profile view with GitHub SSO data and developer stats (robuste sur les emails)"""
    github_user = None
    github_organizations = None
    sync_error = None
    form = UserProfileForm(instance=request.user.userprofile)
    github_emails_list = []
    github_emails_api_status = None
    github_emails_api_raw = None

    # Récupérer le SocialAccount GitHub
    social_account = SocialAccount.objects.filter(user=request.user, provider='github').first()
    github_emails = set()
    # Correction : récupérer le token de façon robuste
    token = SocialToken.objects.filter(account__user=request.user, account__provider='github').first()
    if social_account:
        github_user = social_account.extra_data
        # Ajout des emails du SocialAccount
        if 'email' in github_user and github_user['email']:
            github_emails.add(github_user['email'].lower())
        if 'emails' in github_user and isinstance(github_user['emails'], list):
            for email_obj in github_user['emails']:
                if isinstance(email_obj, dict) and 'email' in email_obj:
                    github_emails.add(email_obj['email'].lower())
    # Récupérer la vraie liste d'emails via l'API GitHub même si social_account absent
    github_emails_api_status = None
    github_emails_api_raw = None
    github_emails_list = []
    if token:
        headers = {
            'Authorization': f'Bearer {token.token}',
            'Accept': 'application/vnd.github+json'
        }
        try:
            resp = requests.get('https://api.github.com/user/emails', headers=headers, timeout=10)
            github_emails_api_status = resp.status_code
            try:
                github_emails_api_raw = resp.json()
            except Exception:
                github_emails_api_raw = resp.text
            if resp.status_code == 200:
                github_emails_list = github_emails_api_raw
        except Exception as e:
            github_emails_api_status = str(e)
            github_emails_api_raw = None

    # Emails à tester : email Django + emails GitHub
    user_emails = set()
    if request.user.email:
        user_emails.add(request.user.email.lower())
    user_emails |= github_emails

    # Trouver un alias correspondant à un de ces emails
    alias = MongoDeveloperAlias.objects(email__in=list(user_emails)).first()
    developer = alias.developer if alias and alias.developer else None
    developer_stats = None
    aliases = []
    if developer:
        analytics = AnalyticsService(0)
        developer_stats = analytics.get_developer_detailed_stats(str(developer.id))
        aliases = MongoDeveloperAlias.objects(developer=developer)
        developer_for_template = type('Developer', (), {
            'name': developer.primary_name,
            'email': developer.primary_email,
            'commit_count': developer_stats.get('total_commits', 0),
            'is_developer': True,
            'github_id': developer.github_id,
            'aliases': aliases
        })()
        from analytics.models import Commit
        alias_emails = [alias.email for alias in aliases]
        all_commits = Commit.objects.filter(author_email__in=alias_emails)
        from developers.views import _calculate_detailed_quality_metrics, _calculate_commit_type_distribution, _calculate_quality_metrics_by_month
        detailed_quality_metrics = _calculate_detailed_quality_metrics(all_commits)
        commit_type_data = _calculate_commit_type_distribution(all_commits)
        quality_metrics_by_month = _calculate_quality_metrics_by_month(all_commits)
        polar_chart_data = []
        for repo in developer_stats.get('top_repositories', []):
            net_lines = repo.get('additions', 0) - repo.get('deletions', 0)
            polar_chart_data.append({
                'label': repo['name'],
                'data': [net_lines],
                'backgroundColor': f'rgba({hash(repo["name"]) % 256}, {(hash(repo["name"]) >> 8) % 256}, {(hash(repo["name"]) >> 16) % 256}, 0.6)',
                'borderColor': f'rgba({hash(repo["name"]) % 256}, {(hash(repo["name"]) >> 8) % 256}, {(hash(repo["name"]) >> 16) % 256}, 1)',
                'borderWidth': 2
            })
        if not polar_chart_data:
            polar_chart_data = []
        from datetime import datetime, timedelta
        now = datetime.utcnow().replace(tzinfo=None)
        cutoff = now - timedelta(days=365)
        commits_365d = [c for c in all_commits if c.authored_date and c.authored_date.replace(tzinfo=None) >= cutoff]
        repo_bubbles = {}
        for commit in commits_365d:
            repo = commit.repository_full_name or 'unknown'
            commit_dt = commit.get_authored_date_in_timezone()
            days_ago = (now.date() - commit_dt.date()).days
            hour = commit_dt.hour
            key = (days_ago, hour)
            if repo not in repo_bubbles:
                repo_bubbles[repo] = {}
            if key not in repo_bubbles[repo]:
                repo_bubbles[repo][key] = {'commits': 0, 'changes': 0}
            repo_bubbles[repo][key]['commits'] += 1
            repo_bubbles[repo][key]['changes'] += (commit.additions or 0) + (commit.deletions or 0)
        palette = [
            {'bg': 'rgba(16, 185, 129, 0.6)', 'border': 'rgba(16, 185, 129, 1)'},
            {'bg': 'rgba(59, 130, 246, 0.6)', 'border': 'rgba(59, 130, 246, 1)'},
            {'bg': 'rgba(245, 158, 11, 0.6)', 'border': 'rgba(245, 158, 11, 1)'},
            {'bg': 'rgba(139, 92, 246, 0.6)', 'border': 'rgba(139, 92, 246, 1)'},
            {'bg': 'rgba(236, 72, 153, 0.6)', 'border': 'rgba(236, 72, 153, 1)'},
            {'bg': 'rgba(34, 197, 94, 0.6)', 'border': 'rgba(34, 197, 94, 1)'},
        ]
        chart_data = []
        for i, (repo, bubbles) in enumerate(repo_bubbles.items()):
            color = palette[i % len(palette)]
            dataset = {
                'label': repo,
                'data': [],
                'backgroundColor': color['bg'],
                'borderColor': color['border'],
                'borderWidth': 1
            }
            for (days_ago, hour), data in bubbles.items():
                dataset['data'].append({
                    'x': days_ago,
                    'y': hour,
                    'r': min(5 + data['commits'] * 2, 20),
                    'commit_count': data['commits'],
                    'changes': data['changes']
                })
            chart_data.append(dataset)
        def _get_commit_type_color(commit_type):
            colors = {
                'fix': '#4caf50',
                'feature': '#2196f3',
                'docs': '#ffeb3b',
                'refactor': '#ff9800',
                'test': '#9c27b0',
                'style': '#00bcd4',
                'chore': '#607d8b',
                'other': '#bdbdbd'
            }
            return colors.get(commit_type, '#bdbdbd')
        commit_type_legend = [
            {'label': k, 'count': v, 'color': _get_commit_type_color(k)}
            for k, v in commit_type_data['counts'].items()
        ] if 'counts' in commit_type_data else []
        first_commit = None
        last_commit = None
        if developer_stats.get('first_commit_date'):
            from analytics.models import Commit
            first_commit = Commit.objects.filter(author_email__in=alias_emails).order_by('authored_date').first()
        if developer_stats.get('last_commit_date'):
            from analytics.models import Commit
            last_commit = Commit.objects.filter(author_email__in=alias_emails).order_by('-authored_date').first()
        commit_frequency = analytics.get_developer_commit_frequency(all_commits)
        context = {
            'form': form,
            'github_user': github_user,
            'github_organizations': github_organizations,
            'sync_error': sync_error,
            'developer': developer_for_template,
            'developer_id': str(developer.id),
            'aliases': aliases,
            'commit_frequency': commit_frequency,
            'commit_quality': developer_stats.get('commit_quality', {}),
            'quality_metrics': detailed_quality_metrics,
            'first_commit': first_commit,
            'last_commit': last_commit,
            'polar_chart_data': polar_chart_data,
            'quality_metrics_by_month': quality_metrics_by_month,
            'chart_data': chart_data,
            'commit_type_distribution': commit_type_data,
            'commit_type_labels': list(commit_type_data['counts'].keys()) if 'counts' in commit_type_data else [],
            'commit_type_values': list(commit_type_data['counts'].values()) if 'counts' in commit_type_data else [],
            'commit_type_legend': commit_type_legend,
            'github_emails_list': github_emails_list,
            'github_emails_api_status': github_emails_api_status,
            'github_emails_api_raw': github_emails_api_raw,
        }
    else:
        context = {
            'form': form,
            'github_user': github_user,
            'github_organizations': github_organizations,
            'sync_error': sync_error,
            'github_emails_list': github_emails_list,
            'github_emails_api_status': github_emails_api_status,
            'github_emails_api_raw': github_emails_api_raw,
        }
    return render(request, 'users/profile.html', context)


def home_view(request):
    """Home view - redirects to login if not authenticated"""
    if request.user.is_authenticated:
        return redirect('users:dashboard')
    return redirect('users:login')


@login_required
def dashboard_view(request):
    """Dashboard view"""
    total_repositories = Repository.objects.count()  # Django ORM, comme sur /repositories/
    total_commits = Commit.objects().count()  # mongoengine
    total_pull_requests = PullRequest.objects().count()  # mongoengine
    total_releases = Release.objects().count()  # mongoengine

    # Commits du mois (30 derniers jours)
    cutoff_date = timezone.now() - timezone.timedelta(days=30)
    recent_commits = Commit.objects.filter(authored_date__gte=cutoff_date)

    # Top développeurs (par Developer global, nom principal)
    dev_stats = defaultdict(int)
    alias_to_developer = {}
    # Préparer un mapping email -> Developer
    for alias in DeveloperAlias.objects.filter(developer__ne=None):
        alias_to_developer[alias.email.lower()] = alias.developer
    for commit in recent_commits:
        dev = alias_to_developer.get(commit.author_email.lower())
        if dev:
            key = dev.primary_name.strip()
        else:
            key = commit.author_name.strip()
        dev_stats[key] += 1
    top_developers = [{'name': name, 'commits': count} for name, count in sorted(dev_stats.items(), key=lambda x: -x[1])[:5]]

    # Top repositories (par nom)
    repo_stats = defaultdict(int)
    for commit in recent_commits:
        key = commit.repository_full_name.strip()
        repo_stats[key] += 1
    top_repositories = [{'repo': repo, 'commits': count} for repo, count in sorted(repo_stats.items(), key=lambda x: -x[1])[:5]]

    context = {
        'total_repositories': total_repositories,
        'total_commits': total_commits,
        'total_pull_requests': total_pull_requests,
        'total_releases': total_releases,
        'top_developers': top_developers,
        'top_repositories': top_repositories,
    }
    return render(request, 'users/dashboard.html', context)
