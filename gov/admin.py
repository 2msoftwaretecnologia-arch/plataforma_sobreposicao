from django.contrib import admin
from .models import Sigef , Ruralsettlement , SnicTotal
# Register your models here.
from leaflet.admin import LeafletGeoAdmin

class SigefAdmin(LeafletGeoAdmin):   
    list_display = ('name', 'installment_code', 'property_code', 'status', 'hash_id', 'area_ha')
    search_fields = ('name',)
    
    fieldsets = (
        (None, {
            'fields': ('name', 'installment_code', 'property_code', 'status', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(Sigef, SigefAdmin)


class RuralsettlementAdmin(LeafletGeoAdmin):
    list_display = ('project_name', 'method_obtaining', 'hash_id', 'area_ha')
    search_fields = ('project_name',)
    
    fieldsets = (
        (None, {
            'fields': ('project_name', 'method_obtaining', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )

admin.site.register(Ruralsettlement, RuralsettlementAdmin)

class SnicTotalAdmin(LeafletGeoAdmin):
    list_display = ('property_name', 'property_code', 'hash_id', 'area_ha')
    search_fields = ('property_name',)
    
    fieldsets = (
        (None, {
            'fields': ('property_name', 'property_code', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(SnicTotal, SnicTotalAdmin)