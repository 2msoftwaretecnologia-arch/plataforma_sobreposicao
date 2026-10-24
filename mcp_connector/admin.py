from django.contrib import admin

from .models import McpAuditLog


@admin.register(McpAuditLog)
class McpAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'tool', 'success')
    list_filter = ('tool', 'success')
    search_fields = ('user__username', 'tool')
    readonly_fields = ('created_at', 'user', 'tool', 'arguments', 'success', 'error')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
