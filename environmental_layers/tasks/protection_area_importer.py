import geopandas as gpd

from environmental_layers.models import EnvironmentalProtectionArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class EnvironmentalProtectionAreaImporter(BulkShapefileImporter):
    model = EnvironmentalProtectionArea
    archive_field = "environmental_protection_zip_file"
    source = "Base APA"

    def missing_archive_message(self):
        return "Nenhum arquivo de APA foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "unit_name": row.get("Unidades"),
            "domains": row.get("Dominios"),
            "class_group": row.get("Classes"),
            "legal_basis": row.get("FundLegal"),
        }
