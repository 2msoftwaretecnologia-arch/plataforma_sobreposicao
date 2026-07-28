from deforestation_fires.models import DeforestationMapbiomas
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class DeforestationMapbiomasImporter(BulkShapefileImporter):
    model = DeforestationMapbiomas
    archive_field = "deforestation_mapbiomas_zip_file"
    source = "Base Deforestation Mapbiomas"

    def missing_archive_message(self):
        return "Nenhum arquivo de Deforestation Mapbiomas foi configurado."

    def format_fields(self, row):
        return {
            "alert_code": str(row.get("CODEALERTA")),
            "detection_year": str(row.get("ANODETEC")),
        }
