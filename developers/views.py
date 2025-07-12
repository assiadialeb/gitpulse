from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from applications.models import Application
from analytics.analytics_service import AnalyticsService


@login_required
def developer_list(request):
    """
    Display paginated list of all grouped developers from all applications
    """
    # Get all applications owned by the user
    user_applications = Application.objects.filter(owner=request.user)
    
    # Collect all grouped developers from all applications
    all_developers = []
    
    for application in user_applications:
        analytics = AnalyticsService(application.id)
        grouped_developers = analytics.get_grouped_developers()
        
        # Add application context to each developer
        for developer in grouped_developers:
            developer['application'] = {
                'id': application.id,
                'name': application.name
            }
        
        all_developers.extend(grouped_developers)
    
    # Sort all developers by primary name (case-insensitive)
    all_developers.sort(key=lambda x: x['primary_name'].lower())
    
    # Pagination
    paginator = Paginator(all_developers, 20)  # 20 developers per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_developers': len(all_developers),
    }
    
    return render(request, 'developers/list.html', context)


@login_required
def developer_detail(request, group_id):
    """
    Display detailed statistics for a specific developer group
    """
    # Get all applications owned by the user
    user_applications = Application.objects.filter(owner=request.user)
    
    # Find the developer and their application
    developer = None
    application = None
    
    for app in user_applications:
        analytics = AnalyticsService(app.id)
        grouped_developers = analytics.get_grouped_developers()
        
        for dev in grouped_developers:
            if dev['group_id'] == group_id:
                developer = dev
                application = app
                break
        
        if developer:
            break
    
    if not developer or not application:
        # Developer not found, redirect to list
        from django.shortcuts import redirect
        return redirect('developers:list')
    
    # Add application context to developer
    developer['application'] = {
        'id': application.id,
        'name': application.name
    }
    
    # Get detailed statistics for this developer
    analytics = AnalyticsService(application.id)
    developer_stats = analytics.get_developer_detailed_stats(group_id)
    
    context = {
        'application': application,
        'developer': developer,
        'stats': developer_stats,
    }
    
    return render(request, 'developers/detail.html', context)


@login_required
@require_http_methods(["GET"])
def api_developer_stats(request, group_id):
    """
    API endpoint to get developer statistics
    """
    # Get all applications owned by the user
    user_applications = Application.objects.filter(owner=request.user)
    
    # Find the developer and their application
    developer = None
    application = None
    
    for app in user_applications:
        analytics = AnalyticsService(app.id)
        grouped_developers = analytics.get_grouped_developers()
        
        for dev in grouped_developers:
            if dev['group_id'] == group_id:
                developer = dev
                application = app
                break
        
        if developer:
            break
    
    if not developer or not application:
        return JsonResponse({'error': 'Developer not found'}, status=404)
    
    analytics = AnalyticsService(application.id)
    stats = analytics.get_developer_detailed_stats(group_id)
    
    return JsonResponse(stats)
