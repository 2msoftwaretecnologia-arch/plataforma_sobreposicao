from gov.models import Ruralsettlement
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs_gml

# Projetos de assentamento do Tocantins, direto do i3Geo do Acervo Fundiário
# do INCRA (WFS), sem shapefile.
I3GEO_URL = "https://acervofundiario.incra.gov.br/i3geo/ogc.php"
LAYER = "assentamentos_to"


class RuralsettlementImporter(BulkShapefileImporter):
    model = Ruralsettlement
    archive_field = "ruralsettlement_zip_file"
    source = "Base Assentamento Rural"

    def missing_archive_message(self):
        return "Nenhum arquivo de assentamento rural foi configurado."

    def load_dataframe(self):
        return fetch_wfs_gml(I3GEO_URL, LAYER, sort_by="gid", extra_params={"tema": LAYER})

    def format_fields(self, row):
        # Nomes completos na API; abreviados (shapefile) nas versões antigas.
        return {
            "project_name": row.get("nome_projeto") or row.get("nome_proje"),
            "method_obtaining": row.get("forma_obtencao") or row.get("forma_obte"),
        }
