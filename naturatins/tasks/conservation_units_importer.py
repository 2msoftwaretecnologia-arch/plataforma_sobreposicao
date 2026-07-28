from naturatins.models import ConservationUnits
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class ConservationUnitsImporter(BulkShapefileImporter):
    model = ConservationUnits
    archive_field = "conservation_units_zip_file"
    source = "Base Unidades de Conservação"

    def missing_archive_message(self):
        return "Nenhum arquivo de unidades de conservação foi configurado."

    def format_fields(self, row):
        return {
            "unit": row.get("Unidades"),
            "domain": row.get("Dominios"),
        }
