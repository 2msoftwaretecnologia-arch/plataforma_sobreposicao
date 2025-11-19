from django.contrib import admin
from .models import ZoningArea, PhytoecologyArea, IndigenousArea, EnvironmentalProtectionArea
# Register your models here.
from leaflet.admin import LeafletGeoAdmin


class ZoningAreaAdmin(LeafletGeoAdmin):
    list_display = ('zone_name', 'zone_acronym', 'area_ha')
    search_fields = ('zone_name', 'zone_acronym')

    readonly_fields = (
        'bbox_display',
        'centroid_display',
        'area_m2',
        'area_ha',
    )

    fieldsets = (
        (None, {
            'fields': (
                'zone_name', 
                'zone_acronym',
                'geometry',
                'bbox_display',
                'centroid_display',
            )
        }),
        (None, {
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )

    # === CAMPOS CALCULADOS ===

    def bbox_display(self, obj):
        if not obj.geometry_new:
            return "—"
        minx, miny, maxx, maxy = obj.geometry_new.extent
        return f"({minx:.4f}, {miny:.4f}) — ({maxx:.4f}, {maxy:.4f})"
    bbox_display.short_description = "Bounding Box"

    def centroid_display(self, obj):
        if not obj.geometry_new:
            return "—"
        c = obj.geometry_new.centroid
        return f"{c.y:.5f}, {c.x:.5f}"
    centroid_display.short_description = "Centro (Lat, Lng)"

admin.site.register(ZoningArea, ZoningAreaAdmin)

class PhytoecologyAreaAdmin(LeafletGeoAdmin):   
    list_display = ('phyto_name', 'hash_id', 'area_ha')
    search_fields = ('phyto_name',)
    
    fieldsets = (
        (None, {
            'fields': ('phyto_name', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(PhytoecologyArea, PhytoecologyAreaAdmin)

class EnvironmentalProtectionAreaAdmin(LeafletGeoAdmin):
    list_display = ('unit_name', 'domains', 'class_group', 'legal_basis', 'hash_id', 'area_ha')
    search_fields = ('unit_name', 'domains', 'class_group')
    
    fieldsets = (
        (None, {
            'fields': ('unit_name', 'domains', 'class_group', 'legal_basis', 'hash_id', 'geometry')
        }),
        (None, {
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
            'area_m2',
            'area_ha',
        )
    
admin.site.register(EnvironmentalProtectionArea, EnvironmentalProtectionAreaAdmin)

class IndigenousAreaAdmin(LeafletGeoAdmin):
    list_display = ('indigenous_name', 'hash_id', 'area_ha')
    search_fields = ('indigenous_name',)
        
    fieldsets = (
        (None, {
            'fields': ('indigenous_name', 'hash_id', 'geometry')
        }),   
        (None, {
            'fields': ('geometry_new', 'area_m2', 'area_ha')
        }),
    )
    
    readonly_fields = (
        'area_m2',
        'area_ha',
    )
        
admin.site.register(IndigenousArea, IndigenousAreaAdmin)
