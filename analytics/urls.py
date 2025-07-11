"""
URLs for analytics dashboard
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Developer grouping
    path('application/<int:application_id>/group-developers/', views.group_developers, name='group_developers'),
    
    # API endpoints
    path('api/application/<int:application_id>/developer-activity/', views.api_developer_activity, name='api_developer_activity'),
    path('api/application/<int:application_id>/activity-heatmap/', views.api_activity_heatmap, name='api_activity_heatmap'),
    path('api/application/<int:application_id>/code-distribution/', views.api_code_distribution, name='api_code_distribution'),
    path('api/application/<int:application_id>/commit-quality/', views.api_commit_quality, name='api_commit_quality'),
    path('api/application/<int:application_id>/group-developers/', views.api_group_developers, name='api_group_developers'),
    path('api/application/<int:application_id>/manual-group-developers/', views.api_manual_group_developers, name='api_manual_group_developers'),
    
    # Indexing endpoints
    path('application/<int:application_id>/start-indexing/', views.start_indexing, name='start_indexing'),
    path('application/<int:application_id>/indexing-progress/', views.get_indexing_progress, name='get_indexing_progress'),
    path('application/<int:application_id>/group/<str:group_id>/delete/', views.delete_group, name='delete_group'),
    path('application/<int:application_id>/group/<str:group_id>/rename/', views.rename_group, name='rename_group'),
    
    # Rate limit management
    path('api/rate-limit-status/', views.get_rate_limit_status, name='get_rate_limit_status'),
    path('api/rate-limit-restart/<str:reset_id>/cancel/', views.cancel_rate_limit_restart, name='cancel_rate_limit_restart'),
] 