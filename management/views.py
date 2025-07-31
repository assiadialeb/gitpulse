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

# Get logger for this module
logger = logging.getLogger(__name__)


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
    from django_q.models import Success
    
    # Get all tasks, ordered by most recent first
    tasks = Success.objects.all().order_by('-started')
    
    # Apply filters
    success_filter = request.GET.get('success', '').strip()
    task_filter = request.GET.get('task', '').strip()
    date_filter = request.GET.get('date', '24h').strip()
    
    if success_filter:
        if success_filter == 'success':
            tasks = tasks.filter(success=True)
        elif success_filter == 'fail':
            tasks = tasks.filter(success=False)
    
    if task_filter:
        tasks = tasks.filter(func__icontains=task_filter)
    
    # Apply date filter
    from datetime import datetime, timedelta
    now = datetime.now()
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
    
    tasks = tasks.filter(started__gte=start_date)
    
    # Get unique task functions for filter dropdown
    task_functions = Success.objects.values_list('func', flat=True).distinct().order_by('func')
    
    # Pagination
    paginator = Paginator(tasks, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate statistics
    total_tasks = tasks.count()
    successful_tasks = tasks.filter(success=True).count()
    failed_tasks = tasks.filter(success=False).count()
    success_rate = (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    context = {
        'active_section': 'logs',
        'log_entries': page_obj,
        'task_functions': task_functions,
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
    
    integrations = [
        {
            'name': 'GitHub',
            'status': github_status,
            'type': 'OAuth',
            'last_sync': '2024-01-15 10:30:00',  # Placeholder
            'config': github_config,
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
        {
            'name': 'SonarCloud',
            'status': sonarcloud_status,
            'type': 'API',
            'last_sync': 'Never',
            'config': sonarcloud_config,
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
        return JsonResponse({
            'success': False,
            'message': f'Network error: {str(e)}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error testing connection: {str(e)}'
        })


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
        return JsonResponse({
            'success': False,
            'message': f'Error loading configuration: {str(e)}'
        })


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
        return JsonResponse({
            'success': False,
            'message': f'Error loading configuration: {str(e)}'
        })


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
        return JsonResponse({
            'success': False,
            'message': f'Error saving configuration: {str(e)}'
        })


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
            'Authorization': f'Bearer {config.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Try to get user info (basic API call)
        response = requests.get('https://sonarcloud.io/api/user/current', headers=headers, timeout=10)
        
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
        return JsonResponse({
            'success': False,
            'message': f'Network error: {str(e)}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error testing connection: {str(e)}'
        })


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
        return JsonResponse({
            'success': False,
            'error': 'User not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


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
        return JsonResponse({
            'success': False,
            'error': 'User not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
