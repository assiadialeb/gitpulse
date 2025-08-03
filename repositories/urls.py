from django.urls import path
from . import views
from . import debug_views
from . import simple_views
from . import working_views

app_name = 'repositories'

urlpatterns = [
    path('', views.repository_list, name='list'),
    path('<int:repo_id>/', working_views.working_repository_detail, name='detail'),
    path('<int:repo_id>/original/', views.repository_detail, name='detail_original'),
    path('<int:repo_id>/simple/', simple_views.simple_repository_detail, name='detail_simple'),
    path('<int:repo_id>/debug/', debug_views.repository_debug, name='debug'),
    path('search/', views.search_repositories, name='search'),
    path('index/', views.index_repository, name='index'),
    path('index-batch/', views.index_repositories, name='index_batch'),
    path('<int:repo_id>/start-indexing/', views.start_indexing, name='start_indexing'),
    path('<int:repo_id>/delete/', views.delete_repository, name='delete'),
    
    # API endpoints for metrics
    path('api/<int:repo_id>/pr-health-metrics/', views.api_repository_pr_health_metrics, name='api_pr_health_metrics'),
    path('api/<int:repo_id>/developer-activity/', views.api_repository_developer_activity, name='api_developer_activity'),
    path('api/<int:repo_id>/commit-quality/', views.api_repository_commit_quality, name='api_commit_quality'),
    path('api/<int:repo_id>/commit-types/', views.api_repository_commit_types, name='api_commit_types'),
    path('api/<int:repo_id>/licensing-analysis/', views.repository_licensing_analysis, name='api_licensing_analysis'),
    path('api/<int:repo_id>/vulnerabilities-analysis/', views.repository_vulnerabilities_analysis, name='api_vulnerabilities_analysis'),
    path('api/<int:repo_id>/llm-license-analysis/', views.repository_llm_license_analysis, name='api_llm_license_analysis'),
    path('api/<int:repo_id>/llm-license-verdict/', views.repository_llm_license_verdict, name='api_llm_license_verdict'),
    path('api/<int:repo_id>/commits/', views.repository_commits_list, name='api_commits_list'),
] 