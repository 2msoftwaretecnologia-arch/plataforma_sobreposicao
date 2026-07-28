from naturatins.models import Paths
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class PathsImporter(BulkShapefileImporter):
    model = Paths
    archive_field = "paths_zip_file"
    source = "Base Veredas"

    def missing_archive_message(self):
        return "Nenhum arquivo de veredas foi configurado."

    def format_fields(self, row):
        return {}
