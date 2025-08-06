"""
URLs for developers app
"""
from django.urls import path
from . import views

app_name = 'developers'

urlpatterns = [
    path('', views.list_developers, name='list'),
    path('search/', views.search_developers_ajax, name='search_ajax'),
    path('search-teams/', views.search_teams_ajax, name='search_teams_ajax'),
    path('search-aliases/', views.search_aliases_ajax, name='search_aliases_ajax'),
    path('merge/', views.merge_developers, name='merge'),
    path('create-from-aliases/', views.create_developer_from_aliases, name='create_from_aliases'),
    path('debug-identity/', views.debug_identity_issues, name='debug_identity'),
    path('sync-github-teams/', views.sync_github_teams, name='sync_github_teams'),
    path('<str:developer_id>/update-name/', views.update_developer_name, name='update_name'),
    path('<str:developer_id>/remove-alias/<str:alias_id>/', views.remove_developer_alias, name='remove_alias'),
    path('<str:developer_id>/', views.developer_detail, name='detail'),
] 