import geopandas as gpd

from gov.models import Ruralsettlement
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class RuralsettlementImporter(BulkShapefileImporter):
    model = Ruralsettlement
    archive_field = "ruralsettlement_zip_file"
    source = "Base Assentamento Rural"

    def missing_archive_message(self):
        return "Nenhum arquivo de assentamento rural foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "project_name": row.get("nome_proje"),
            "method_obtaining": row.get("forma_obte"),
        }
