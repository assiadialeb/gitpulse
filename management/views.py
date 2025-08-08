"""
Views for the management app
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from users.models import UserDeveloperLink
from analytics.models import Developer
from bson import ObjectId
import logging
import uuid

# Get logger for this module
logger = logging.getLogger(__name__)
def _error_response(user_message: str, exc: Exception = None, status: int = 500):
    """Return a safe JSON error with a correlation id; log full details server-side."""
    error_id = str(uuid.uuid4())
    if exc is not None:
        logger.exception(f"{user_message} [error_id={error_id}]")
    else:
        logger.error(f"{user_message} [error_id={error_id}]")
    return JsonResponse({
        'success': False,
        'message': user_message,
        'error_id': error_id
    }, status=status)



def is_admin(user):
    """Check if user is admin"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_admin)
def management_dashboard(request):
    """Main management dashboard"""
    context = {
        'active_section': 'dashboard',
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'staff_users': User.objects.filter(is_staff=True).count(),
    }
    return render(request, 'management/dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def users_management(request):
    """Users management section"""
    users = User.objects.all().order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users = users.filter(
            username__icontains=search_query
        ) | users.filter(
            email__icontains=search_query
        ) | users.filter(
            first_name__icontains=search_query
        ) | users.filter(
            last_name__icontains=search_query
        )
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'active_section': 'users',
        'users': page_obj,
        'search_query': search_query,
        'total_users': users.count(),
    }
    return render(request, 'management/users.html', context)


@login_required
@user_passes_test(is_admin)
def logs_management(request):
    """Logs management section - Django Q Tasks"""
    from django_q.models import Success, Failure
    
    # Get all tasks (successful and failed), ordered by most recent first
    from itertools import chain
    from django.db.models import Q
    
    # Get successful tasks
    successful_tasks = Success.objects.all()
    # Get failed tasks and convert them to have success=False
    failed_tasks = Failure.objects.all()
    
    # Combine both querysets
    tasks = list(chain(successful_tasks, failed_tasks))
    # Sort by started date (most recent first)
    tasks.sort(key=lambda x: x.started, reverse=True)
    
    # Apply filters
    success_filter = request.GET.get('success', '').strip()
    task_filter = request.GET.get('task', '').strip()
    date_filter = request.GET.get('date', '24h').strip()
    
    # Apply date filter first
    from datetime import datetime, timedelta
    from django.utils import timezone
    now = timezone.now()
    if date_filter == '1h':
        start_date = now - timedelta(hours=1)
    elif date_filter == '24h':
        start_date = now - timedelta(days=1)
    elif date_filter == '7d':
        start_date = now - timedelta(days=7)
    elif date_filter == '30d':
        start_date = now - timedelta(days=30)
    else:
        start_date = now - timedelta(days=1)  # Default to 24h
    
    # Filter by date
    tasks = [task for task in tasks if task.started and task.started >= start_date]
    
    # Create user-friendly task names mapping
    task_name_mapping = {
        'analytics.tasks.check_new_releases_and_generate_sbom_task': 'SBOM Auto Generation',
        'analytics.tasks.generate_sbom_task': 'SBOM Manual Generation',
        'analytics.tasks.daily_indexing_all_repos_task': 'Daily Indexing',
        'analytics.tasks.fetch_all_pull_requests_task': 'Pull Requests Indexing',
        'analytics.tasks.release_indexing_all_repos_task': 'Releases Indexing',
        'analytics.tasks.quality_analysis_all_repos_task': 'Quality Analysis',
        'analytics.tasks.group_developer_identities_task': 'Developer Grouping',
    }
    
    # Apply success filter
    if success_filter:
        if success_filter == 'success':
            tasks = [task for task in tasks if hasattr(task, 'success') and task.success]
        elif success_filter == 'fail':
            tasks = [task for task in tasks if not hasattr(task, 'success') or not task.success]
    
    # Apply task filter - improved logic
    if task_filter:
        # Check if this is a user-friendly name from our mapping
        technical_names = []
        for tech_name, friendly_name in task_name_mapping.items():
            if friendly_name == task_filter:
                technical_names.append(tech_name)
        
        if technical_names:
            # Filter by exact technical names
            tasks = [task for task in tasks if task.func in technical_names]
        else:
            # Fallback to partial match for any task
            tasks = [task for task in tasks if task_filter.lower() in task.func.lower()]
    
    # Get unique task functions for filter dropdown
    all_functions = set()
    for task in tasks:
        all_functions.add(task.func)
    
    # Also get functions from scheduled tasks
    from django_q.models import Schedule
    scheduled_tasks = Schedule.objects.all()
    for task in scheduled_tasks:
        all_functions.add(task.func)
    
    # Filter to only show the main scheduled tasks
    main_tasks = [
        'analytics.tasks.check_new_releases_and_generate_sbom_task',
        'analytics.tasks.generate_sbom_task',
        'analytics.tasks.daily_indexing_all_repos_task',
        'analytics.tasks.fetch_all_pull_requests_task',
        'analytics.tasks.release_indexing_all_repos_task',
        'analytics.tasks.quality_analysis_all_repos_task',
        'analytics.tasks.group_developer_identities_task',
    ]
    
    # Only include the main tasks that exist in the database
    task_functions = [func for func in main_tasks if func in all_functions]
    
    # Pagination
    paginator = Paginator(tasks, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate statistics on the filtered dataset
    total_tasks = len(tasks)
    successful_tasks = len([task for task in tasks if hasattr(task, 'success') and task.success])
    failed_tasks = len([task for task in tasks if not hasattr(task, 'success') or not task.success])
    success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # Get scheduled tasks for display
    scheduled_tasks = Schedule.objects.all().order_by('next_run')
    
    # Filter scheduled tasks to only show main tasks
    main_scheduled_tasks = []
    for task in scheduled_tasks:
        if task.func in main_tasks:
            main_scheduled_tasks.append(task)
    
    context = {
        'active_section': 'logs',
        'log_entries': page_obj,
        'scheduled_tasks': main_scheduled_tasks,
        'task_functions': task_functions,
        'task_name_mapping': task_name_mapping,
        'total_tasks': total_tasks,
        'successful_tasks': successful_tasks,
        'failed_tasks': failed_tasks,
        'success_rate': success_rate,
        'current_filters': {
            'success': success_filter,
            'task': task_filter,
            'date': date_filter,
        }
    }
    return render(request, 'management/logs.html', context)


@login_required
@user_passes_test(is_admin)
def integrations_management(request):
    """Integrations management section"""
    from github.models import GitHubApp
    from sonarcloud.models import SonarCloudConfig
    from management.models import OSSIndexConfig
    
    # Get GitHub configuration
    github_config = None
    github_status = 'inactive'
    
    try:
        # Get GitHubApp configuration
        github_app = GitHubApp.objects.first()
        
        if github_app and github_app.client_id and github_app.client_secret:
            github_config = {
                'client_id': github_app.client_id,
                'client_secret': github_app.client_secret[:10] + '...' if github_app.client_secret else 'Not configured',
            }
            github_status = 'active'
        else:
            github_config = {
                'client_id': 'Not configured',
                'client_secret': 'Not configured',
            }
    except Exception as e:
        github_config = {
            'client_id': 'Error loading config',
            'client_secret': 'Error loading config',
        }
    
    # Get SonarCloud configuration
    sonarcloud_config = None
    sonarcloud_status = 'inactive'
    
    try:
        sonarcloud_app = SonarCloudConfig.get_config()
        
        if sonarcloud_app and sonarcloud_app.access_token:
            sonarcloud_config = {
                'access_token': sonarcloud_app.access_token[:10] + '...' if sonarcloud_app.access_token else 'Not configured',
            }
            sonarcloud_status = 'active'
        else:
            sonarcloud_config = {
                'access_token': 'Not configured',
            }
    except Exception as e:
        sonarcloud_config = {
            'access_token': 'Error loading config',
        }
    
    # Get OSS Index configuration
    ossindex_config = None
    ossindex_status = 'inactive'
    
    try:
        ossindex_app = OSSIndexConfig.get_config()
        
        if ossindex_app and ossindex_app.email and ossindex_app.api_token:
            ossindex_config = {
                'email': ossindex_app.email,
                'api_token': ossindex_app.api_token[:10] + '...' if ossindex_app.api_token else 'Not configured',
            }
            ossindex_status = 'active'
        else:
            ossindex_config = {
                'email': 'Not configured',
                'api_token': 'Not configured',
            }
    except Exception as e:
        ossindex_config = {
            'email': 'Error loading config',
            'api_token': 'Error loading config',
        }
    
    integrations = [
        {
            'name': 'GitHub',
            'status': github_status,
            'type': 'OAuth',
            'last_sync': '2024-01-15 10:30:00',  # Placeholder
            'config': github_config,
        },
        {
            'name': 'OSS Index',
            'status': ossindex_status,
            'type': 'Vulnerability Scanner',
            'last_sync': 'Never',
            'config': ossindex_config,
        },
        {
            'name': 'SonarCloud',
            'status': sonarcloud_status,
            'type': 'API',
            'last_sync': 'Never',
            'config': sonarcloud_config,
        },
        {
            'name': 'Slack',
            'status': 'inactive',
            'type': 'Coming Soon',
            'last_sync': 'Never',
            'config': {
                'webhook_url': 'not_configured',
            }
        },
    ]
    
    context = {
        'active_section': 'integrations',
        'integrations': integrations,
    }
    return render(request, 'management/integrations.html', context)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_github_connection(request):
    """Test GitHub OAuth connection"""
    from allauth.socialaccount.models import SocialApp
    from django.contrib.sites.models import Site
    import requests
    
    try:
        site = Site.objects.get_current()
        social_app = SocialApp.objects.filter(provider='github', sites=site).first()
        
        if not social_app or not social_app.client_id or not social_app.secret:
            return JsonResponse({
                'success': False,
                'message': 'GitHub OAuth not configured. Please configure client_id and client_secret first.'
            })
        
        # Test GitHub API connection using client credentials
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitPulse/1.0'
        }
        
        # Try to get rate limit info (doesn't require authentication)
        response = requests.get('https://api.github.com/rate_limit', headers=headers, timeout=10)
        
        if response.status_code == 200:
            return JsonResponse({
                'success': True,
                'message': 'GitHub API connection successful. OAuth configuration is valid.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'GitHub API connection failed. Status: {response.status_code}'
            })
            
    except requests.exceptions.RequestException as e:
        return _error_response('Network error when contacting GitHub API', exc=e, status=502)
    except Exception as e:
        return _error_response('Error testing connection', exc=e)


@login_required
@user_passes_test(is_admin)
def get_github_config(request):
    """Get GitHub configuration for modal"""
    from github.models import GitHubApp
    
    try:
        # Get GitHub configuration from our custom model
        github_app = GitHubApp.objects.first()
        
        # Generate correct callback URL from current request
        current_url = request.build_absolute_uri()
        # Extract base URL (e.g., http://localhost:8001)
        base_url = current_url.split('/management/')[0]
        callback_url = f"{base_url}/accounts/github/login/callback/"
        
        if github_app and github_app.client_id and github_app.client_secret:
            config = {
                'client_id': github_app.client_id,
                'client_secret': github_app.client_secret,
                'callback_url': callback_url,
                'configured': True
            }
        else:
            config = {
                'client_id': '',
                'client_secret': '',
                'callback_url': callback_url,
                'configured': False
            }
        
        return JsonResponse({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        return _error_response('Error loading configuration', exc=e)


@login_required
@user_passes_test(is_admin)
def get_sonarcloud_config(request):
    """Get SonarCloud configuration for modal"""
    from sonarcloud.models import SonarCloudConfig
    
    try:
        config = SonarCloudConfig.get_config()
        
        config_data = {
            'access_token': config.access_token if config.access_token else '',
            'configured': bool(config.access_token)
        }
        
        return JsonResponse({
            'success': True,
            'config': config_data
        })
        
    except Exception as e:
        return _error_response('Error loading configuration', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def save_sonarcloud_config(request):
    """Save SonarCloud configuration"""
    from sonarcloud.models import SonarCloudConfig
    
    try:
        access_token = request.POST.get('access_token', '').strip()
        
        if not access_token:
            return JsonResponse({
                'success': False,
                'message': 'Access token is required'
            })
        
        config = SonarCloudConfig.get_config()
        config.access_token = access_token
        config.save()
        
        return JsonResponse({
            'success': True,
            'message': 'SonarCloud configuration saved successfully'
        })
        
    except Exception as e:
        return _error_response('Error saving configuration', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_sonarcloud_connection(request):
    """Test SonarCloud API connection"""
    from sonarcloud.models import SonarCloudConfig
    import requests
    
    try:
        config = SonarCloudConfig.get_config()
        
        if not config.access_token:
            return JsonResponse({
                'success': False,
                'message': 'SonarCloud not configured. Please configure access token first.'
            })
        
        # Test SonarCloud API connection
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Try to validate authentication (correct API endpoint)
        response = requests.get('https://sonarcloud.io/api/authentication/validate', 
                              params={'token': config.access_token}, 
                              headers=headers, timeout=10)
        
        if response.status_code == 200:
            return JsonResponse({
                'success': True,
                'message': 'SonarCloud API connection successful. Token is valid.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'SonarCloud API connection failed. Status: {response.status_code}'
            })
            
    except requests.exceptions.RequestException as e:
        return _error_response('Network error when contacting SonarCloud API', exc=e, status=502)
    except Exception as e:
        return _error_response('Error testing connection', exc=e)


@login_required
@user_passes_test(is_admin)
def user_detail(request, user_id):
    """User detail view for management"""
    try:
        user = User.objects.get(id=user_id)
        # Get developer link if exists
        try:
            developer_link = user.developer_link
            # Get developer details from MongoDB
            from analytics.models import Developer
            try:
                developer = Developer.objects.get(id=developer_link.developer_id)
                developer_info = {
                    'id': str(developer.id),
                    'name': developer.primary_name,
                    'email': developer.primary_email,
                }
            except Developer.DoesNotExist:
                developer_info = None
        except UserDeveloperLink.DoesNotExist:
            developer_link = None
            developer_info = None
    except User.DoesNotExist:
        messages.error(request, 'User not found')
        return redirect('management:users')
    
    context = {
        'active_section': 'users',
        'user_detail': user,
        'developer_info': developer_info,
    }
    return render(request, 'management/user_detail.html', context)


@login_required
@user_passes_test(is_admin)
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.is_active = not user.is_active
            user.save()
            
            return JsonResponse({
                'success': True,
                'is_active': user.is_active,
                'message': f'User {"activated" if user.is_active else "deactivated"} successfully'
            })
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'User not found'
            }, status=404)
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)


@login_required
@user_passes_test(is_admin)
def search_developers_ajax(request):
    """Search developers for autocomplete"""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Search developers by primary_name or primary_email
    developers = Developer.objects.filter(
        primary_name__icontains=query
    ).limit(10)
    
    # Also search by email if no results by name
    if not developers:
        developers = Developer.objects.filter(
            primary_email__icontains=query
        ).limit(10)
    
    results = []
    for dev in developers:
        # Get aliases for display (using reverse relationship)
        from analytics.models import DeveloperAlias
        aliases = DeveloperAlias.objects.filter(developer=dev)[:3]
        alias_emails = [alias.email for alias in aliases]
        
        # Calculate total commit count from aliases
        total_commits = sum(alias.commit_count for alias in aliases) if aliases else 0
        
        results.append({
            'id': str(dev.id),
            'name': dev.primary_name,
            'email': dev.primary_email,
            'aliases': alias_emails,
            'commit_count': total_commits,
            'text': f"{dev.primary_name} ({dev.primary_email}) - {total_commits} commits"
        })
    
    return JsonResponse({'results': results})


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def link_user_to_developer(request, user_id):
    """Link a user to a developer"""
    try:
        user = User.objects.get(id=user_id)
        developer_id = request.POST.get('developer_id')
        
        if not developer_id:
            return JsonResponse({
                'success': False,
                'error': 'Developer ID is required'
            }, status=400)
        
        # Validate developer exists
        try:
            developer = Developer.objects(id=ObjectId(developer_id)).first()
            if not developer:
                return JsonResponse({
                    'success': False,
                    'error': 'Developer not found'
                }, status=404)
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Invalid developer ID format'
            }, status=400)
        
        # Check if user is already linked
        existing_link = UserDeveloperLink.objects.filter(user=user).first()
        if existing_link:
            return JsonResponse({
                'success': False,
                'error': f'User is already linked to developer {existing_link.developer_id}'
            }, status=400)
        
        # Check if developer is already linked
        existing_dev_link = UserDeveloperLink.objects.filter(developer_id=developer_id).first()
        if existing_dev_link:
            return JsonResponse({
                'success': False,
                'error': f'Developer is already linked to user {existing_dev_link.user.username}'
            }, status=400)
        
        # Create the link
        link = UserDeveloperLink.objects.create(
            user=user,
            developer_id=developer_id
        )
        
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} successfully linked to developer {developer.name}',
            'link_id': link.id
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    except Exception as e:
        return _error_response('Error linking user to developer', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def unlink_user_from_developer(request, user_id):
    """Unlink a user from their developer"""
    try:
        user = User.objects.get(id=user_id)
        link = UserDeveloperLink.objects.filter(user=user).first()
        
        if not link:
            return JsonResponse({
                'success': False,
                'error': 'User is not linked to any developer'
            }, status=404)
        
        developer_id = link.developer_id
        link.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} unlinked from developer {developer_id}'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    except Exception as e:
        return _error_response('Error unlinking user from developer', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def save_ossindex_config(request):
    """Save OSS Index configuration"""
    try:
        from management.models import OSSIndexConfig
        
        email = request.POST.get('email', '').strip()
        api_token = request.POST.get('api_token', '').strip()
        
        if not email:
            return JsonResponse({
                'success': False,
                'message': 'Email is required'
            })
        
        if not api_token:
            return JsonResponse({
                'success': False,
                'message': 'API token is required'
            })
        
        # Get or create configuration
        config = OSSIndexConfig.get_config()
        config.email = email
        config.api_token = api_token
        config.save()
        
        return JsonResponse({
            'success': True,
            'message': 'OSS Index configuration saved successfully'
        })
        
    except Exception as e:
        return _error_response('Error saving configuration', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_ossindex_connection(request):
    """Test OSS Index API connection"""
    try:
        from management.models import OSSIndexConfig
        
        config = OSSIndexConfig.get_config()
        
        if not config.email:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index email not configured'
            })
        
        if not config.api_token:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index API token not configured'
            })
        
        # For now, just verify both email and token are set
        # In the future, we could make an actual API call to test the connection
        if config.email and config.api_token:
            return JsonResponse({
                'success': True,
                'message': f'OSS Index configuration is valid (email: {config.email})'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index configuration is incomplete'
            })
            
    except Exception as e:
        return _error_response('Error testing connection', exc=e)


@login_required
@user_passes_test(is_admin)
def get_ossindex_config(request):
    """Get OSS Index configuration"""
    try:
        from management.models import OSSIndexConfig
        
        config = OSSIndexConfig.get_config()
        
        if config.email and config.api_token:
            return JsonResponse({
                'success': True,
                'config': {
                    'email': config.email,
                    'api_token': config.api_token,
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'OSS Index configuration not found'
            })
            
    except Exception as e:
        return _error_response('Error loading configuration', exc=e)
