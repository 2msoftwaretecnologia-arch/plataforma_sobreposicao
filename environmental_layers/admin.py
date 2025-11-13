from django.contrib import admin
from .models import ZoningArea, PhytoecologyArea, EnvironmentalProtectionArea
# Register your models here.

class ZoningAreaAdmin(admin.ModelAdmin):
    list_display = ('zone_name', 'zone_acronym')
    search_fields = ('zone_name', 'zone_acronym')
    
    fieldsets = (
        (None, {
            'fields': ('zone_name', 'zone_acronym', 'geometry')
        }),
    )
admin.site.register(ZoningArea, ZoningAreaAdmin)

class PhytoecologyAreaAdmin(admin.ModelAdmin):
    list_display = ('phyto_name', 'hash_id')
    search_fields = ('phyto_name',)
    
    fieldsets = (
        (None, {
            'fields': ('phyto_name', 'hash_id', 'geometry')
        }),
    )
    
admin.site.register(PhytoecologyArea, PhytoecologyAreaAdmin)

class EnvironmentalProtectionAreaAdmin(admin.ModelAdmin):
    list_display = ('unit_name', 'domains', 'class_group', 'legal_basis', 'hash_id')
    search_fields = ('unit_name', 'domains', 'class_group')
    
    fieldsets = (
        (None, {
            'fields': ('unit_name', 'domains', 'class_group', 'legal_basis', 'hash_id', 'geometry')
        }),
    )
admin.site.register(EnvironmentalProtectionArea, EnvironmentalProtectionAreaAdmin)