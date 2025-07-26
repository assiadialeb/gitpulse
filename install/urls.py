from django.urls import path
from . import views

app_name = 'install'

urlpatterns = [
    path('', views.install_view, name='install'),
] 