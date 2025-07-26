from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django_q.tasks import schedule
from django_q.models import Schedule
from .forms import SuperUserCreationForm, GitHubOAuthForm
from .models import InstallationStep, InstallationLog
from github.models import GitHubApp


def installation_required(view_func):
    """Decorator to check if installation is required"""
    def wrapper(request, *args, **kwargs):
        if User.objects.count() > 0:
            messages.error(request, 'Installation already completed. Cannot access installation wizard.')
            return redirect('users:login')
        return view_func(request, *args, **kwargs)
    return wrapper


@installation_required
def install_view(request):
    """Main installation wizard view"""
    if request.method == 'POST':
        return handle_installation(request)
    
    # Check if we have existing data
    has_github_app = bool(GitHubApp.objects.first())
    
    context = {
        'superuser_form': SuperUserCreationForm(),
        'github_form': GitHubOAuthForm(),
        'has_github_app': has_github_app,
    }
    
    return render(request, 'install/install.html', context)


def handle_installation(request):
    """Handle the installation form submission"""
    superuser_form = SuperUserCreationForm(request.POST)
    github_form = GitHubOAuthForm(request.POST)
    
    if superuser_form.is_valid() and github_form.is_valid():
        try:
            # Create superuser
            user = superuser_form.save()
            log_installation('SUCCESS', f'SuperUser created: {user.username}')
            
            # Configure GitHub OAuth
            github_app = github_form.save()
            log_installation('SUCCESS', f'GitHub OAuth configured with client ID: {github_app.client_id[:10]}...')
            
            # Setup scheduled tasks
            if setup_scheduled_tasks():
                log_installation('SUCCESS', 'Scheduled tasks configured successfully')
            else:
                log_installation('WARNING', 'Some scheduled tasks failed to configure')
            
            messages.success(request, 'Installation completed successfully! You can now log in and start using GitPulse.')
            return redirect('users:login')
            
        except Exception as e:
            log_installation('ERROR', f'Installation failed: {str(e)}')
            messages.error(request, f'Installation failed: {str(e)}')
    else:
        # Log form errors
        if not superuser_form.is_valid():
            log_installation('ERROR', f'SuperUser form errors: {superuser_form.errors}')
        if not github_form.is_valid():
            log_installation('ERROR', f'GitHub form errors: {github_form.errors}')
    
    context = {
        'superuser_form': superuser_form,
        'github_form': github_form,
        'has_github_app': bool(GitHubApp.objects.first()),
    }
    
    return render(request, 'install/install.html', context)


def setup_scheduled_tasks():
    """Setup the scheduled tasks for analytics"""
    tasks = [
        ('analytics.tasks.quality_analysis_all_repos_task', 0),  # 00:00
        ('analytics.tasks.group_developer_identities_task', 1),  # 01:00
        ('analytics.tasks.index_all_commits_task', 2),          # 02:00
        ('analytics.tasks.index_all_pullrequests_task', 3),     # 03:00
        ('analytics.tasks.index_all_releases_task', 4),         # 04:00
        ('analytics.tasks.index_all_deployments_task', 5),      # 05:00
    ]
    
    success_count = 0
    for task_name, hour in tasks:
        try:
            # Delete existing schedule if it exists
            Schedule.objects.filter(func=task_name).delete()
            
            # Create new schedule
            schedule(
                func=task_name,
                schedule_type=Schedule.HOURLY,
                minutes=0,
                hours=hour,
                repeats=-1,  # Repeat indefinitely
            )
            success_count += 1
            log_installation('INFO', f'Scheduled task: {task_name} at {hour:02d}:00')
        except Exception as e:
            log_installation('ERROR', f'Failed to schedule {task_name}: {str(e)}')
    
    return success_count == len(tasks)


def log_installation(level, message):
    """Log installation events"""
    InstallationLog.objects.create(
        level=level,
        message=message
    )
