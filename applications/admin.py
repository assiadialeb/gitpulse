from django.contrib import admin
from .models import Application, ApplicationRepository


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'repository_count', 'created_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['name', 'description', 'owner__username']
    readonly_fields = ['created_at', 'updated_at']
    
    def repository_count(self, obj):
        return obj.repository_count
    repository_count.short_description = 'Repositories'


@admin.register(ApplicationRepository)
class ApplicationRepositoryAdmin(admin.ModelAdmin):
    list_display = ['github_repo_name', 'application', 'language', 'stars_count', 'forks_count', 'is_private', 'added_at']
    list_filter = ['is_private', 'language', 'added_at']
    search_fields = ['github_repo_name', 'application__name', 'description']
    readonly_fields = ['github_repo_id', 'added_at', 'last_updated']
    
    fieldsets = (
        ('Repository Information', {
            'fields': ('application', 'github_repo_name', 'github_repo_id', 'description')
        }),
        ('GitHub Details', {
            'fields': ('default_branch', 'is_private', 'language', 'stars_count', 'forks_count')
        }),
        ('Timestamps', {
            'fields': ('last_updated', 'added_at'),
            'classes': ('collapse',)
        }),
    )
