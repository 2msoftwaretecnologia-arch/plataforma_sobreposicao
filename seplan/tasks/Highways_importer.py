from seplan.models import Highways
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class HighwaysImporter(BulkShapefileImporter):
    model = Highways
    archive_field = "highways_zip_file"
    source = "Base Highways"

    def missing_archive_message(self):
        return "Nenhum arquivo de highways foi configurado."

    def format_fields(self, row):
        return {
            "NOME_2011": row.get("NOME_2011") or "Sem Nome",
            "CLAS_2011": row.get("CLAS_2011") or "Sem Classe",
        }
