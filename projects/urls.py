from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    path('', views.project_list, name='list'),
    path('<int:project_id>/', views.project_detail, name='detail'),
    path('create/', views.project_create, name='create'),
    path('<int:project_id>/edit/', views.project_edit, name='edit'),
    path('<int:project_id>/delete/', views.project_delete, name='delete'),
] 