import geopandas as gpd

from environmental_layers.models import PhytoecologyArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class PhytoecologyAreaImporter(BulkShapefileImporter):
    model = PhytoecologyArea
    archive_field = "phytoecology_zip_file"
    source = "Base Fitoecologia"

    def missing_archive_message(self):
        return "Nenhum arquivo de fitoecologia foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "phyto_name": row.get("AnáliseCA"),
        }
