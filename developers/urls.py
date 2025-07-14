"""
URLs for developers app
"""
from django.urls import path
from . import views

app_name = 'developers'

urlpatterns = [
    path('', views.list_developers, name='list'),
    path('search/', views.search_developers_ajax, name='search_ajax'),
    path('merge/', views.merge_developers, name='merge'),
    path('<str:developer_id>/update-name/', views.update_developer_name, name='update_name'),
    path('<str:developer_id>/', views.developer_detail, name='detail'),
] 