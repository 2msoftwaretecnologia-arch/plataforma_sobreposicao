import geopandas as gpd

from gov.models import SnicTotal
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class SnicTotalImporter(BulkShapefileImporter):
    model = SnicTotal
    archive_field = "snic_total_zip_file"
    source = "Base SnicTotal"

    def missing_archive_message(self):
        return "Nenhum arquivo de SnicTotal foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "property_name": row.get("nome_imove"),
            "property_code": row.get("cod_imovel"),
        }
