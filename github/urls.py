from django.urls import path
from . import views

app_name = 'github'

urlpatterns = [
    path('admin/', views.admin_view, name='admin'),
    path('admin-simple/', views.admin_simple, name='admin_simple'),
    path('token-help/', views.token_help, name='token_help'),
    path('test-access/', views.test_github_access, name='test_access'),
    path('force-reauth/', views.force_github_reauth, name='force_reauth'),
    path('connection-status/', views.github_connection_status, name='connection_status'),
    path('unified-setup/', views.unified_setup, name='unified_setup'),
] 