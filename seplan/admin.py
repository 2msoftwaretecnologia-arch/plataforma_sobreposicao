from django.contrib import admin
from .models import Highways, Ipuca
from leaflet.admin import LeafletGeoAdmin

class HighwaysAdmin(LeafletGeoAdmin):
    list_display = ('NOME_2011', 'CLAS_2011', 'hash_id', 'area_ha')
    search_fields = ('NOME_2011', 'CLAS_2011')
    
    fieldsets = (
        (None, {
            'fields': ('NOME_2011', 'CLAS_2011', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
        'area_m2',
        'area_ha',
    )

admin.site.register(Highways, HighwaysAdmin)

class IpucaAdmin(LeafletGeoAdmin):
    list_display = ('hash_id', 'area_ha')
    search_fields = ('hash_id',)
    
    fieldsets = (
        (None, {
            'fields': ('hash_id', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
        'area_m2',
        'area_ha',
    )

admin.site.register(Ipuca, IpucaAdmin)
