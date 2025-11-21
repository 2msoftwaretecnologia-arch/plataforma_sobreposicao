from django.contrib import admin

from .models import FileManagement

class FileManagementAdmin(admin.ModelAdmin):
    list_display = (
        'phytoecology_zip_file',
        'environmental_protection_zip_file',
        'zoning_zip_file',
        'sicar_zip_file',
        'indigenous_zip_file',
        'quilombolas_zip_file',
        'paths_zip_file',
        'municipal_boundaries_zip_file',
        'sigef_zip_file',
        'ruralsettlement_zip_file',
    )
    
    list_display_links = (
        'phytoecology_zip_file',
        'environmental_protection_zip_file',
        'zoning_zip_file',
        'sicar_zip_file',
        'indigenous_zip_file',
        'quilombolas_zip_file',
        'paths_zip_file',
        'municipal_boundaries_zip_file',
        'sigef_zip_file',
        'ruralsettlement_zip_file',
    )
    
    search_fields = (
        'phytoecology_zip_file',
        'environmental_protection_zip_file',
        'zoning_zip_file',
        'sicar_zip_file',
        'indigenous_zip_file',
        'quilombolas_zip_file',
        'paths_zip_file',
        'municipal_boundaries_zip_file',
        'sigef_zip_file',
        'ruralsettlement_zip_file',
    )
    
    def has_add_permission(self, request):
        return not FileManagement.objects.exists()

admin.site.register(FileManagement, FileManagementAdmin)
    
    
