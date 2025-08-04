from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django_q.tasks import schedule
from django_q.models import Schedule
from datetime import datetime, timedelta
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
    
    # Daily tasks (run once per day at specific hours)
    daily_tasks = [
        # ('analytics.tasks.daily_indexing_all_repos_task', 0),   # 00:00 - Daily indexing for all repos (DISABLED - using specialized tasks instead)
        # ('analytics.tasks.group_developer_identities_task', 1), # 01:00 - Group developer identities (DISABLED - manual control)
        ('analytics.tasks.index_all_commits_task', 2),          # 02:00 - Index all commits
        ('analytics.tasks.index_all_pullrequests_task', 3),     # 03:00 - Index all PRs
        ('analytics.tasks.index_all_releases_task', 4),         # 04:00 - Index all releases
        ('analytics.tasks.index_all_deployments_task', 5),      # 05:00 - Index all deployments
        ('analytics.tasks.check_new_releases_and_generate_sbom_task', 6), # 06:00 - Check new releases and generate SBOM
        ('analytics.services.index_all_sonarcloud_metrics_task', 7), # 07:00 - Index all SonarCloud metrics
    ]
    
    # Periodic tasks (run every X minutes/hours)
    periodic_tasks = [
        ('analytics.services.process_pending_rate_limit_restarts', 5),  # Every 5 minutes
        ('analytics.tasks.fetch_all_pull_requests_task', 180),         # Every 3 hours (180 minutes)
    ]
    
    success_count = 0
    
    # Setup daily tasks
    for task_name, hour in daily_tasks:
        try:
            # Delete existing schedule if it exists
            Schedule.objects.filter(func=task_name).delete()
            
            # Create new schedule
            next_run = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
            # If the time has already passed today, schedule for tomorrow
            if next_run <= timezone.now():
                next_run = next_run + timedelta(days=1)
            
            # Create descriptive name for the schedule
            schedule_name = f"daily_{task_name.split('.')[-1].replace('_task', '')}_{hour:02d}h00"
            
            Schedule.objects.create(
                name=schedule_name,
                func=task_name,
                schedule_type=Schedule.DAILY,
                next_run=next_run,
                repeats=-1,  # Repeat indefinitely
            )
            success_count += 1
            log_installation('INFO', f'Scheduled daily task: {schedule_name} ({task_name}) at {hour:02d}:00')
        except Exception as e:
            log_installation('ERROR', f'Failed to schedule {task_name}: {str(e)}')
    
    # Setup periodic tasks
    for task_name, minutes in periodic_tasks:
        try:
            # Delete existing schedule if it exists
            Schedule.objects.filter(func=task_name).delete()
            
            # Create descriptive name for the schedule
            if minutes < 60:
                schedule_name = f"every_{minutes}m_{task_name.split('.')[-1]}"
            else:
                hours = minutes // 60
                schedule_name = f"every_{hours}h_{task_name.split('.')[-1]}"
            
            Schedule.objects.create(
                name=schedule_name,
                func=task_name,
                schedule_type=Schedule.MINUTES,
                minutes=minutes,
                repeats=-1,  # Repeat indefinitely
            )
            success_count += 1
            log_installation('INFO', f'Scheduled periodic task: {schedule_name} ({task_name}) every {minutes} minutes')
        except Exception as e:
            log_installation('ERROR', f'Failed to schedule {task_name}: {str(e)}')
    
    # Setup cleanup task (daily at 2 AM)
    try:
        cleanup_schedule, cleanup_created = Schedule.objects.get_or_create(
            name='cleanup_old_rate_limit_resets',
            defaults={
                'func': 'analytics.services.cleanup_old_rate_limit_resets',
                'schedule_type': Schedule.DAILY,
                'next_run': timezone.now().replace(hour=2, minute=0, second=0, microsecond=0),
                'repeats': -1  # Infinite repeats
            }
        )
        if cleanup_created:
            log_installation('INFO', 'Created rate limit cleanup task (daily at 2 AM)')
            success_count += 1
        else:
            log_installation('INFO', 'Rate limit cleanup task already exists')
            success_count += 1
        
    except Exception as e:
        log_installation('ERROR', f'Failed to setup rate limit cleanup task: {str(e)}')
    
    total_expected_tasks = len(daily_tasks) + len(periodic_tasks) + 1  # +1 for cleanup task
    return success_count == total_expected_tasks


def log_installation(level, message):
    """Log installation events"""
    InstallationLog.objects.create(
        level=level,
        message=message
    )
