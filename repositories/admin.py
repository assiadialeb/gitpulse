from django.contrib import admin
from .models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'owner', 'language', 'stars', 'forks', 'is_indexed', 'commit_count', 'created_at']
    list_filter = ['is_indexed', 'private', 'fork', 'language', 'created_at']
    search_fields = ['name', 'full_name', 'description']
    readonly_fields = ['github_id', 'html_url', 'clone_url', 'ssh_url', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'full_name', 'description', 'owner')
        }),
        ('Repository Details', {
            'fields': ('private', 'fork', 'language', 'stars', 'forks', 'size', 'default_branch')
        }),
        ('GitHub Metadata', {
            'fields': ('github_id', 'html_url', 'clone_url', 'ssh_url'),
            'classes': ('collapse',)
        }),
        ('Indexing Status', {
            'fields': ('is_indexed', 'last_indexed', 'commit_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
