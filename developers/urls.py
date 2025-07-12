from django.urls import path
from . import views

app_name = 'developers'

urlpatterns = [
    path('', views.developer_list, name='list'),
    path('<str:group_id>/', views.developer_detail, name='detail'),
    path('<str:group_id>/stats/', views.api_developer_stats, name='api_stats'),
] 