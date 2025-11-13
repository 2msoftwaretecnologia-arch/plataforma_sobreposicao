from django.contrib import admin
from car_system.models import SicarRecord

@admin.register(SicarRecord)
class SicarRecordAdmin(admin.ModelAdmin):
    list_display = ('car_number', 'status', 'last_update', 'created_at', 'updated_at')
    search_fields = ('car_number', 'status')
    list_filter = ('status', 'last_update')
    
    fieldsets = (
        (None, {
            'fields': ('car_number', 'status', 'last_update', 'geometry', 'created_by', 'source')
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    list_per_page = 200

