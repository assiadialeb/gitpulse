from django.contrib import admin
from .models import OSSIndexConfig


@admin.register(OSSIndexConfig)
class OSSIndexConfigAdmin(admin.ModelAdmin):
    list_display = ('updated_at', 'has_token')
    readonly_fields = ('created_at', 'updated_at')
    
    def has_token(self, obj):
        return bool(obj.api_token)
    has_token.boolean = True
    has_token.short_description = 'Token Configured' 