from django.contrib import admin
from .models import DeforestationMapbiomas
# Register your models here.
from leaflet.admin import LeafletGeoAdmin



class DeforestationMapbiomasAdmin(LeafletGeoAdmin):   
    list_display = ('alert_code', 'detection_year', 'source', 'area_ha')
    search_fields = ('alert_code',)
    
    fieldsets = (
        (None, {
            'fields': ('alert_code', 'detection_year', 'source', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(DeforestationMapbiomas, DeforestationMapbiomasAdmin)

