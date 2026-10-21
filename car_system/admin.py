from django.contrib import admin
from car_system.models import (
    SicarRecord,
    DeclaredHydrography,
    CarEstadual2023,
    DeclaredApp,
    DeclaredNativeVegetation,
    DeclaredLegalReserve,
    DeclaredConsolidatedArea,
    DeclaredRestrictedUse,
    DeclaredFallowArea,
    DeclaredAdministrativeEasement,
)
from leaflet.admin import LeafletGeoAdmin

@admin.register(SicarRecord)
class SicarRecordAdmin(LeafletGeoAdmin):
    list_display = ('id', 'car_number', 'status', 'area_ha')
    search_fields = ('car_number', 'status')
    list_filter = ('status', 'last_update')
    
    fieldsets = (
        (None, {
            'fields': ('car_number', 'status', 'last_update', 'geometry', 'created_by', 'source')
        }),
        (None, {
            'fields': (
                'usable_geometry',
                'area_m2',
                'area_ha',
                'bbox_display',
                'centroid_display',)
        }),
    )
    
    readonly_fields = ('created_at', 
                       'updated_at', 
                       'area_m2',
                        'area_ha',
                        'bbox_display',
                        'centroid_display')
    
    list_per_page = 200

    def bbox_display(self, obj):
        if not obj.usable_geometry:
            return "—"
        minx, miny, maxx, maxy = obj.usable_geometry.extent
        return f"({minx:.4f}, {miny:.4f}) — ({maxx:.4f}, {maxy:.4f})"
    bbox_display.short_description = "Bounding Box"

    def centroid_display(self, obj):
        if not obj.usable_geometry:
            return "—"
        c = obj.usable_geometry.centroid
        return f"{c.y:.5f}, {c.x:.5f}"
    centroid_display.short_description = "Centro (Lat, Lng)"


@admin.register(DeclaredHydrography)
class DeclaredHydrographyAdmin(LeafletGeoAdmin):
    list_display = ('id', 'car_number', 'category_source', 'pending', 'area_ha')
    search_fields = ('car_number', 'category_source')
    list_filter = ('category_source', 'pending')

    fieldsets = (
        (None, {
            'fields': ('car_number', 'category_source', 'pending', 'geometry', 'created_by', 'source')
        }),
        (None, {
            'fields': (
                'usable_geometry',
                'area_m2',
                'area_ha',
                'bbox_display',
                'centroid_display',)
        }),
    )

    readonly_fields = ('created_at',
                       'updated_at',
                       'area_m2',
                        'area_ha',
                        'bbox_display',
                        'centroid_display')

    list_per_page = 200

    def bbox_display(self, obj):
        if not obj.usable_geometry:
            return "—"
        minx, miny, maxx, maxy = obj.usable_geometry.extent
        return f"({minx:.4f}, {miny:.4f}) — ({maxx:.4f}, {maxy:.4f})"
    bbox_display.short_description = "Bounding Box"

    def centroid_display(self, obj):
        if not obj.usable_geometry:
            return "—"
        c = obj.usable_geometry.centroid
        return f"{c.y:.5f}, {c.x:.5f}"
    centroid_display.short_description = "Centro (Lat, Lng)"


@admin.register(CarEstadual2023)
class CarEstadual2023Admin(LeafletGeoAdmin):
    list_display = ('id', 'car_number', 'federal_car_number', 'property_name', 'status', 'city', 'area_ha')
    search_fields = ('car_number', 'federal_car_number', 'property_name', 'information')
    list_filter = ('status', 'city')
    readonly_fields = ('created_at', 'updated_at', 'area_m2', 'area_ha')
    list_per_page = 200


class DeclaredSicarThemeAdmin(LeafletGeoAdmin):
    list_display = ('id', 'car_number', 'category_source', 'city', 'pending', 'area_ha')
    search_fields = ('car_number', 'category_source')
    list_filter = ('category_source', 'car_status', 'city')
    readonly_fields = ('created_at', 'updated_at', 'area_m2', 'area_ha')
    list_per_page = 200


for _model in (
    DeclaredApp,
    DeclaredNativeVegetation,
    DeclaredLegalReserve,
    DeclaredConsolidatedArea,
    DeclaredRestrictedUse,
    DeclaredFallowArea,
    DeclaredAdministrativeEasement,
):
    admin.site.register(_model, DeclaredSicarThemeAdmin)
