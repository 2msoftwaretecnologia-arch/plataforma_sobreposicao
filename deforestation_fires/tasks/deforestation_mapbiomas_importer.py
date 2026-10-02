from deforestation_fires.models import DeforestationMapbiomas
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs

# Alertas de desmatamento do MapBiomas Alerta (polígonos) direto do GeoServer
# público deles, sem login nem shapefile. A API GraphQL da plataforma exige
# conta (e cada login derruba o anterior) e não devolve o polígono, só o
# ponto e o retângulo do alerta, por isso o WFS.
WFS_URL = "https://maps.alerta.mapbiomas.org/geoserver/ows"
LAYER = "mapbiomas-alertas:dashboard-alert-shapefile"
# `states` vem em maiúsculas e pode listar mais de um estado.
CQL_TOCANTINS = "states LIKE '%TOCANTINS%'"
PROPERTIES = "alert_code,year_detected_at,geom"


class DeforestationMapbiomasImporter(BulkShapefileImporter):
    model = DeforestationMapbiomas
    archive_field = "deforestation_mapbiomas_zip_file"
    source = "MapBiomas Alerta"

    def missing_archive_message(self):
        return "Nenhum arquivo de Deforestation Mapbiomas foi configurado."

    def load_dataframe(self):
        return fetch_wfs(WFS_URL, LAYER, cql_filter=CQL_TOCANTINS, properties=PROPERTIES, sort_by="alert_code")

    def natural_key(self, row):
        return row.get("alert_code")

    def format_fields(self, row):
        return {
            "alert_code": str(row.get("alert_code")),
            "detection_year": str(row.get("year_detected_at")),
        }
