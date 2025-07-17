from django.urls import path
from . import views

app_name = 'github'

urlpatterns = [
    path('admin/', views.admin_view, name='admin'),
] 