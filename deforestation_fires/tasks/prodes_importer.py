from deforestation_fires.models import Prodes
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class ProdesImporter(BulkShapefileImporter):
    model = Prodes
    archive_field = "prodes_zip_file"
    source = "Prodes"

    def missing_archive_message(self):
        return "Nenhum arquivo de Prodes foi configurado."

    def format_fields(self, row):
        return {
            "identification": str(row.get("main_class")),
            "image_date": str(row.get("image_date")),
            "year": str(row.get("year")),
            "satelite": str(row.get("satelite")),
        }
