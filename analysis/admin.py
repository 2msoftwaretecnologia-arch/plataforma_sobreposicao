from django.contrib import admin

from .models import SearchHistory


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'search_type', 'car_input', 'municipio', 'uf', 'sucesso', 'created_at')
    list_filter = ('search_type', 'sucesso', 'uf')
    search_fields = ('car_input', 'municipio', 'user__username')
    readonly_fields = [f.name for f in SearchHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
