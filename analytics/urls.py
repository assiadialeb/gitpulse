"""
URLs for analytics dashboard
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # API endpoints
    path('api/application/<int:application_id>/developer-activity/', views.api_developer_activity, name='api_developer_activity'),
    path('api/application/<int:application_id>/activity-heatmap/', views.api_activity_heatmap, name='api_activity_heatmap'),
    path('api/application/<int:application_id>/code-distribution/', views.api_code_distribution, name='api_code_distribution'),
    path('api/application/<int:application_id>/commit-quality/', views.api_commit_quality, name='api_commit_quality'),
    path('api/application/<int:application_id>/commit-types/', views.api_commit_types, name='api_commit_types'),
    path('api/applications/<int:application_id>/auto-group-developers/', views.api_auto_group_developers, name='api_auto_group_developers'),
    path('api/applications/<int:application_id>/merge-existing-groups/', views.api_merge_existing_groups, name='api_merge_existing_groups'),
    path('api/applications/<int:application_id>/manual-group-developers/', views.api_manual_group_developers, name='api_manual_group_developers'),
    
    # Indexing endpoints
    path('application/<int:application_id>/start-indexing/', views.start_indexing, name='start_indexing'),
    path('application/<int:application_id>/indexing-progress/', views.get_indexing_progress, name='get_indexing_progress'),
] 