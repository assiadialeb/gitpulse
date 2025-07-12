from django.urls import path
from . import views

app_name = 'applications'

urlpatterns = [
    path('', views.application_list, name='list'),
    path('create/', views.application_create, name='create'),
    path('<int:pk>/', views.application_detail, name='detail'),
    path('<int:pk>/edit/', views.application_edit, name='edit'),
    path('<int:pk>/delete/', views.application_delete, name='delete'),
    path('<int:pk>/add-repositories/', views.add_repositories, name='add_repositories'),
    path('<int:pk>/api/repositories/', views.api_get_repositories, name='api_get_repositories'),
    path('<int:pk>/remove-repository/<int:repo_id>/', views.remove_repository, name='remove_repository'),
    path('debug/github/', views.debug_github, name='debug_github'),
] 