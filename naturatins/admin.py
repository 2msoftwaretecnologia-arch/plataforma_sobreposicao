from django.contrib import admin
from .models import Quilombolas
# Register your models here.
from leaflet.admin import LeafletGeoAdmin



class QuilombolasAdmin(LeafletGeoAdmin):   
    list_display = ('name', 'hash_id', 'area_ha')
    search_fields = ('name',)
    
    fieldsets = (
        (None, {
            'fields': ('name', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(Quilombolas, QuilombolasAdmin)
