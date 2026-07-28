from datetime import datetime

import geopandas as gpd

from car_system.models import SicarRecord
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class SicarImporter(BulkShapefileImporter):
    model = SicarRecord
    archive_field = "sicar_zip_file"
    source = "Base Sicar"

    def missing_archive_message(self):
        return "Nenhum arquivo de SICAR foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    @staticmethod
    def format_date(date_str):
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except (ValueError, TypeError):
            return None

    def format_fields(self, row):
        return {
            "car_number": row.get("cod_imovel"),
            "status": row.get("ind_status"),
            "last_update": self.format_date(row.get("dat_atuali")),
        }

    def natural_key(self, row):
        return row.get("cod_imovel")
