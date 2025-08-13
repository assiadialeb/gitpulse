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
import requests

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
        # Quality analysis removed - metrics are calculated in real-time
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
        # Quality analysis removed - metrics are calculated in real-time
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
    from allauth.socialaccount.models import SocialApp
    from sonarcloud.models import SonarCloudConfig
    from .models import IntegrationConfig
    from django.contrib.sites.models import Site
    
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
    
    # Build integrations list from IntegrationConfig for GitHub (multi-org)
    github_integrations = []
    for ic in IntegrationConfig.objects.filter(provider='github').order_by('github_organization', 'name'):
        github_integrations.append({
            'id': ic.id,
            'name': 'GitHub',
            'status': ic.status,
            'type': 'GitHub App',
            'last_sync': 'Never',
            'config': {
                'name': ic.name,
                'organization': ic.github_organization or '',
                'app_id': ic.app_id or '',
            }
        })

    # GitHub SSO (SocialApp) - single instance allowed
    sso_status = 'inactive'
    sso_config = {
        'client_id': 'Not configured',
        'callback_url': '',
    }
    try:
        site = Site.objects.get_current()
        sso_app = SocialApp.objects.filter(provider='github', sites=site).first()
        # Build callback based on current host
        base_url = request.build_absolute_uri('/').rstrip('/')
        sso_callback = f"{base_url}/accounts/github/login/callback/"
        if sso_app and sso_app.client_id and sso_app.secret:
            sso_status = 'active'
            sso_config['client_id'] = sso_app.client_id[:10] + '...'
        sso_config['callback_url'] = sso_callback
    except Exception:
        pass

    # Compose main integrations (excluding SSO)
    integrations = (
        github_integrations
        + [
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
    )
    
    # SSO integrations (separate rubric)
    sso_integrations = [
        {
            'name': 'SSO GitHub',
            'status': sso_status,
            'type': 'OAuth',
            'last_sync': 'Never',
            'config': sso_config,
        }
    ]

    context = {
        'active_section': 'integrations',
        'integrations': integrations,
        'sso_integrations': sso_integrations,
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
@require_http_methods(["POST"]) 
def save_github_config(request):
    """Deprecated: Global GitHub OAuth flow removed."""
    return JsonResponse({'success': False, 'message': 'Global GitHub OAuth is no longer supported. Use GitHub App integrations.'}, status=400)


@login_required
@user_passes_test(is_admin)
def get_sso_github_oauth_config(request):
    """Return GitHub SSO (allauth SocialApp) config for the current Site."""
    from allauth.socialaccount.models import SocialApp
    from django.contrib.sites.models import Site
    try:
        site = Site.objects.get_current()
        app = SocialApp.objects.filter(provider='github', sites=site).first()
        base_url = request.build_absolute_uri('/').rstrip('/')
        callback_url = f"{base_url}/accounts/github/login/callback/"
        if app:
            return JsonResponse({
                'success': True,
                'config': {
                    'client_id': app.client_id or '',
                    'client_secret': app.secret or '',
                    'callback_url': callback_url,
                    'configured': bool(app.client_id and app.secret),
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'config': {
                    'client_id': '',
                    'client_secret': '',
                    'callback_url': callback_url,
                    'configured': False,
                }
            })
    except Exception as e:
        return _error_response('Error loading SSO GitHub configuration', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def save_sso_github_oauth_config(request):
    """Create/update the single GitHub SocialApp for current Site; ensure uniqueness per site."""
    from allauth.socialaccount.models import SocialApp
    from django.contrib.sites.models import Site
    try:
        client_id = request.POST.get('client_id', '').strip()
        client_secret = request.POST.get('client_secret', '').strip()
        if not client_id or not client_secret:
            return JsonResponse({'success': False, 'message': 'Client ID and Client Secret are required'})

        site = Site.objects.get_current()

        # Ensure single SocialApp for provider github on this site
        apps = list(SocialApp.objects.filter(provider='github', sites=site))
        if apps:
            app = apps[0]
            app.client_id = client_id
            app.secret = client_secret
            app.save()
            # Remove this site from any extra apps for uniqueness
            for extra in apps[1:]:
                extra.sites.remove(site)
        else:
            app = SocialApp.objects.create(provider='github', name='GitHub')
            app.client_id = client_id
            app.secret = client_secret
            app.save()
            app.sites.add(site)

        return JsonResponse({'success': True, 'message': 'GitHub SSO configuration saved'})
    except Exception as e:
        return _error_response('Error saving SSO GitHub configuration', exc=e)


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
@require_http_methods(["POST"])
def save_github_integration_instance(request):
    """Create or update a GitHub IntegrationConfig instance (org-specific)."""
    try:
        from .models import IntegrationConfig
        integration_id = request.POST.get('id')
        name = request.POST.get('name', '').strip()
        organization = request.POST.get('organization', '').strip()
        app_id = request.POST.get('app_id', '').strip()
        private_key = request.POST.get('private_key', '').strip()
        status = request.POST.get('status', 'active').strip() or 'active'
        if not name:
            return JsonResponse({'success': False, 'message': 'Name is required'})
        if not organization:
            return JsonResponse({'success': False, 'message': 'Organization is required'})
        if integration_id:
            ic = IntegrationConfig.objects.get(id=integration_id)
        else:
            ic = IntegrationConfig(provider='github')
        ic.name = name
        ic.github_organization = organization
        # On create, require both app_id and private_key. On update, keep existing values if inputs are blank
        if not integration_id:
            if not app_id or not private_key:
                return JsonResponse({'success': False, 'message': 'App ID and Private Key are required'})
            ic.app_id = app_id
            ic.private_key = private_key
        else:
            if app_id:
                ic.app_id = app_id
            if private_key:
                ic.private_key = private_key
        ic.status = status
        ic.save()
        return JsonResponse({'success': True, 'message': 'GitHub integration saved'})
    except IntegrationConfig.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Integration not found'}, status=404)
    except Exception as e:
        return _error_response('Error saving GitHub integration', exc=e)


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def delete_github_integration_instance(request, integration_id: int):
    """Delete a GitHub IntegrationConfig instance."""
    try:
        from .models import IntegrationConfig
        ic = IntegrationConfig.objects.get(id=integration_id)
        ic.delete()
        return JsonResponse({'success': True, 'message': 'GitHub integration deleted'})
    except IntegrationConfig.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Integration not found'}, status=404)
    except Exception as e:
        return _error_response('Error deleting GitHub integration', exc=e)


@login_required
@user_passes_test(is_admin)
def list_user_github_orgs(request):
    """List GitHub organizations accessible to the current user using their OAuth token (if available).
    Falls back to empty list when no token.
    """
    try:
        from allauth.socialaccount.models import SocialToken, SocialApp, SocialAccount
        from django.contrib.sites.models import Site
        user = request.user
        site = Site.objects.get_current()
        app = SocialApp.objects.filter(provider='github', sites=site).first()
        if not app:
            return JsonResponse({'success': True, 'organizations': []})
        account = SocialAccount.objects.filter(user=user, provider='github').first()
        if not account:
            return JsonResponse({'success': True, 'organizations': []})
        token_obj = SocialToken.objects.filter(account=account, app=app).first()
        if not token_obj:
            return JsonResponse({'success': True, 'organizations': []})

        headers = {
            'Authorization': f'token {token_obj.token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'GitPulse'
        }
        orgs = []
        page = 1
        while True:
            resp = requests.get('https://api.github.com/user/orgs', headers=headers, params={'per_page': 100, 'page': page}, timeout=10)
            if resp.status_code != 200:
                break
            batch = resp.json() or []
            for org in batch:
                login = org.get('login')
                if login:
                    orgs.append({'login': login, 'type': 'org', 'label': login})
            if len(batch) < 100:
                break
            page += 1
        # Append user's personal account as last option, if available
        try:
            user_login = (account.extra_data or {}).get('login')
        except Exception:
            user_login = None
        if user_login and all(o.get('login') != user_login for o in orgs):
            orgs.append({'login': user_login, 'type': 'user', 'label': f"{user_login} (personal)"})
        return JsonResponse({'success': True, 'organizations': orgs})
    except Exception as e:
        return _error_response('Error listing GitHub organizations', exc=e)


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
        
        # Check if developer is already linked to another user
        existing_dev_link = UserDeveloperLink.objects.filter(developer_id=developer_id).exclude(user=user).first()
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
            'message': f'User {user.username} successfully linked to developer {developer.primary_name}',
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