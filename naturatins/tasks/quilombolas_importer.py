import geopandas as gpd

from naturatins.models import Quilombolas
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class QuilombolasImporter(BulkShapefileImporter):
    model = Quilombolas
    archive_field = "quilombolas_zip_file"
    source = "Base Quilombolas"

    def missing_archive_message(self):
        return "Nenhum arquivo de quilombolas foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "name": row.get("nm_comunid"),
        }
