from seplan.models import Ipuca
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class IpucaImporter(BulkShapefileImporter):
    model = Ipuca
    archive_field = "ipuca_zip_file"
    source = "Base IPUCA"

    def missing_archive_message(self):
        return "Nenhum arquivo de ipuca foi configurado."

    def format_fields(self, row):
        return {}
