from naturatins.models import MunicipalBoundaries
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class MunicipalBoundariesImporter(BulkShapefileImporter):
    model = MunicipalBoundaries
    archive_field = "municipal_boundaries_zip_file"
    source = "Base Municípios"

    def missing_archive_message(self):
        return "Nenhum arquivo de municípios foi configurado."

    def format_fields(self, row):
        return {
            "name": row.get("NOME"),
        }
