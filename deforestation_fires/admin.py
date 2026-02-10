from django.contrib import admin
from .models import DeforestationMapbiomas, Embargoes , Prodes
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

class EmbargoesAdmin(LeafletGeoAdmin):   
    list_display = ('property_name', 'nome_embargado', 'process_number', 'embargoe_date', 'area_ha')
    search_fields = ('property_name', 'nome_embargado', 'process_number', 'cpf_cnpj_embargado')
    
    fieldsets = (
        (None, {
            'fields': (
                'property_name', 
                'nome_embargado', 
                'cpf_cnpj_embargado', 
                'process_number', 
                'type_area', 
                'number_infraction_act', 
                'control_unity', 
                'act_description', 
                'infraction_description', 
                'embargoe_date', 
                'priting_date', 
                'geometry'
            )
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(Embargoes, EmbargoesAdmin)

class ProdesAdmin(LeafletGeoAdmin):   
    list_display = ('identification', 'image_date', 'year', 'satelite')
    search_fields = ('identification', 'image_date', 'year', 'satelite')
    
    fieldsets = (
        (None, {
            'fields': ('identification', 'image_date', 'year', 'satelite', 'geometry')
        }),
        (None, {
            'fields': ('usable_geometry', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(Prodes, ProdesAdmin)