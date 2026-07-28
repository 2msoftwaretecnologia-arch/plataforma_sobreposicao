from gov.models import Sigef
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class SigefImporter(BulkShapefileImporter):
    model = Sigef
    archive_field = "sigef_zip_file"
    source = "Base Sigef"

    def missing_archive_message(self):
        return "Nenhum arquivo de sigef foi configurado."

    def format_fields(self, row):
        return {
            "name": row.get("nome_area") or "Sem Nome",
            "installment_code": row.get("parcela_co") or "Sem Parcela",
            "property_code": row.get("propriedade_co") or "Sem Propriedade",
            "status": row.get("status") or "Sem Status",
        }
