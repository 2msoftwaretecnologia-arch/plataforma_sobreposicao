import geopandas as gpd

from car_system.models import DeclaredHydrography
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class HydrographyImporter(BulkShapefileImporter):
    model = DeclaredHydrography
    archive_field = "hydrography_zip_file"
    source = "Base Hidrografia Declarada"

    def missing_archive_message(self):
        return "Nenhum arquivo de hidrografia declarada foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        return {
            "category_source": row.get("nom_tema"),
            "car_number": row.get("cod_imovel"),
            "pending": row.get("des_condic"),
        }
