from django.contrib import admin
from .models import Sigef
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
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(Sigef, SigefAdmin)


