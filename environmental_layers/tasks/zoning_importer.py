import geopandas as gpd

from environmental_layers.models import ZoningArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class ZoningAreaImporter(BulkShapefileImporter):
    model = ZoningArea
    archive_field = "zoning_zip_file"
    source = "Base Zoneamento"

    def missing_archive_message(self):
        return "Nenhum arquivo de zoneamento foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "zone_name": row.get("nm_zona"),
            "zone_acronym": row.get("zona_sigla"),
        }
