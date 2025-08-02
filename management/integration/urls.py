from django.urls import path
from . import views

app_name = 'integration'

urlpatterns = [
    path('save-ossindex-config/', views.save_ossindex_config, name='save_ossindex_config'),
    path('test-ossindex-connection/', views.test_ossindex_connection, name='test_ossindex_connection'),
] 