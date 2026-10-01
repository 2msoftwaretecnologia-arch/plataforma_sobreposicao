import geopandas as gpd
import pandas as pd

from deforestation_fires.models import Prodes
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs

# PRODES (desmatamento anual) direto da API WFS do INPE/TerraBrasilis, sem
# shapefile. O Tocantins está nos dois monitoramentos: o do Cerrado (a maior
# parte do estado) e o da Amazônia Legal (florestas do norte). Cada um grafa
# o estado de um jeito.
WFS_URL = "https://terrabrasilis.dpi.inpe.br/geoserver/{workspace}/ows"
PRODES_LAYERS = (
    ("prodes-cerrado-nb", "state='TOCANTINS'"),
    ("prodes-legal-amz", "state='TO'"),
)
PROPERTIES = "main_class,year,image_date,satellite,uuid,geom"


class ProdesImporter(BulkShapefileImporter):
    model = Prodes
    archive_field = "prodes_zip_file"
    source = "Prodes"

    def missing_archive_message(self):
        return "Nenhum arquivo de Prodes foi configurado."

    def load_dataframe(self):
        frames = [
            fetch_wfs(
                WFS_URL.format(workspace=workspace),
                f"{workspace}:yearly_deforestation",
                cql_filter=cql,
                properties=PROPERTIES,
                sort_by="fid",
            )
            for workspace, cql in PRODES_LAYERS
        ]
        return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4674")

    def natural_key(self, row):
        # `hash_id` é único na tabela.
        return row.get("uuid")

    def format_fields(self, row):
        return {
            "identification": str(row.get("main_class")),
            "image_date": str(row.get("image_date")),
            "year": str(row.get("year")),
            "satelite": str(row.get("satellite")),
            "hash_id": row.get("uuid"),
        }
