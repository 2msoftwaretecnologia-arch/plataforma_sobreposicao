from environmental_layers.models import IndigenousArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class IndigenousAreaImporter(BulkShapefileImporter):
    model = IndigenousArea
    archive_field = "indigenous_zip_file"
    source = "Base Indígena"

    def missing_archive_message(self):
        return "Nenhum arquivo de indígena foi configurado."

    def format_fields(self, row):
        return {
            "indigenous_name": row.get("NOME_AREA"),
        }
