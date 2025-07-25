from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'get_total_repositories', 'get_total_commits', 'get_total_developers', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    filter_horizontal = ['repositories']
    
    def get_total_repositories(self, obj):
        return obj.get_total_repositories()
    get_total_repositories.short_description = 'Repositories'
    
    def get_total_commits(self, obj):
        return obj.get_total_commits()
    get_total_commits.short_description = 'Total Commits'
    
    def get_total_developers(self, obj):
        return obj.get_total_developers()
    get_total_developers.short_description = 'Total Developers'
