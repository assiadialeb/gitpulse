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
    """Logs management section"""
    # Get log files or recent log entries
    # This is a placeholder - you can implement actual log viewing
    log_entries = []
    
    # Example log entries (replace with actual log reading)
    log_entries = [
        {
            'timestamp': '2024-01-15 10:30:00',
            'level': 'INFO',
            'message': 'User login successful',
            'user': 'admin',
        },
        {
            'timestamp': '2024-01-15 10:25:00',
            'level': 'WARNING',
            'message': 'Rate limit approaching',
            'user': 'system',
        },
        {
            'timestamp': '2024-01-15 10:20:00',
            'level': 'ERROR',
            'message': 'GitHub API connection failed',
            'user': 'system',
        },
    ]
    
    context = {
        'active_section': 'logs',
        'log_entries': log_entries,
    }
    return render(request, 'management/logs.html', context)


@login_required
@user_passes_test(is_admin)
def integrations_management(request):
    """Integrations management section"""
    # Placeholder for integrations data
    integrations = [
        {
            'name': 'GitHub',
            'status': 'active',
            'type': 'OAuth',
            'last_sync': '2024-01-15 10:30:00',
            'config': {
                'client_id': 'configured',
                'webhooks': 'enabled',
            }
        },
        {
            'name': 'Slack',
            'status': 'inactive',
            'type': 'Webhook',
            'last_sync': 'Never',
            'config': {
                'webhook_url': 'not_configured',
            }
        },
        {
            'name': 'SonarCloud',
            'status': 'inactive',
            'type': 'API',
            'last_sync': 'Never',
            'config': {
                'api_token': 'not_configured',
                'organization': 'not_configured',
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
