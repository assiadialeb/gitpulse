from django.urls import path
from . import views

app_name = 'github'

urlpatterns = [
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback/', views.oauth_callback, name='callback'),
    path('disconnect/', views.disconnect, name='disconnect'),
    path('admin/', views.admin_view, name='admin'),
] 