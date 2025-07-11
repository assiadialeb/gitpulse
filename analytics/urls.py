"""
URLs for analytics dashboard
"""
from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Dashboard
    path('application/<int:application_id>/dashboard/', views.application_dashboard, name='application_dashboard'),
    
    # API endpoints
    path('api/application/<int:application_id>/developer-activity/', views.api_developer_activity, name='api_developer_activity'),
    path('api/application/<int:application_id>/activity-heatmap/', views.api_activity_heatmap, name='api_activity_heatmap'),
    path('api/application/<int:application_id>/code-distribution/', views.api_code_distribution, name='api_code_distribution'),
    path('api/application/<int:application_id>/commit-quality/', views.api_commit_quality, name='api_commit_quality'),
] 