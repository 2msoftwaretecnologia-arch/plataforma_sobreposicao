from environmental_layers.models import ZoningArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs

# Zoneamento Ecológico-Econômico do Tocantins direto do Geoportal da
# SEPLAN-TO (GeoServer), sem shapefile.
WFS_URL = "https://geoportal.to.gov.br/geoserver/ows"
LAYER = "zoneamento_ecologico_economico:zoneamento_to"


class ZoningAreaImporter(BulkShapefileImporter):
    model = ZoningArea
    archive_field = "zoning_zip_file"
    source = "Base Zoneamento"

    def missing_archive_message(self):
        return "Nenhum arquivo de zoneamento foi configurado."

    def load_dataframe(self):
        return fetch_wfs(WFS_URL, LAYER, properties="nm_zona,zona_sigla,geom", sort_by="OBJECTID")

    def format_fields(self, row):
        return {
            "zone_name": row.get("nm_zona"),
            "zone_acronym": row.get("zona_sigla"),
        }
