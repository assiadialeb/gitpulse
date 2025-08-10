"""
URLs for management app
"""
from django.urls import path
from . import views

app_name = 'management'

urlpatterns = [
    # Dashboard
    path('', views.management_dashboard, name='dashboard'),
    
    # Users management
    path('users/', views.users_management, name='users'),
    path('users/<int:user_id>/', views.user_detail, name='user_detail'),
    path('users/<int:user_id>/toggle-status/', views.toggle_user_status, name='toggle_user_status'),
    path('users/search-developers/', views.search_developers_ajax, name='search_developers'),
    path('users/<int:user_id>/link-developer/', views.link_user_to_developer, name='link_user_developer'),
    path('users/<int:user_id>/unlink-developer/', views.unlink_user_from_developer, name='unlink_user_developer'),
    
    # Logs management
    path('logs/', views.logs_management, name='logs'),
    
    # Integrations management
    path('integrations/', views.integrations_management, name='integrations'),
    path('integrations/test-github/', views.test_github_connection, name='test_github_connection'),
    path('integrations/github-config/', views.get_github_config, name='get_github_config'),
    path('integrations/sonarcloud-config/', views.get_sonarcloud_config, name='get_sonarcloud_config'),
    path('integrations/save-sonarcloud/', views.save_sonarcloud_config, name='save_sonarcloud_config'),
    path('integrations/test-sonarcloud/', views.test_sonarcloud_connection, name='test_sonarcloud_connection'),
] 