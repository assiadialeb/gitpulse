from django.urls import path
from . import views

app_name = 'developers'

urlpatterns = [
    path('', views.developer_list, name='list'),
    path('sync/', views.sync_from_mongo, name='sync'),
    path('list_groups/', views.list_groups, name='list_groups'),
    path('create-group/', views.create_group, name='create_group'),
    path('add-to-group/', views.add_to_group, name='add_to_group'),
    path('merge_group/', views.merge_group, name='merge_group'),
    path('add_identity_to_group/', views.add_identity_to_group, name='add_identity_to_group'),
    path('search/', views.search_developers, name='search_developers'),
    path('<str:developer_id>/update-name/', views.update_developer_name, name='update_name'),
    path('<str:developer_id>/', views.developer_detail, name='detail'),
] 