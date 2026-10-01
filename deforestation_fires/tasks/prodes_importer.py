import geopandas as gpd
import pandas as pd
import requests

from deforestation_fires.models import Prodes
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter

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
PAGE_SIZE = 5000
TIMEOUT = 300


class ProdesImporter(BulkShapefileImporter):
    model = Prodes
    archive_field = "prodes_zip_file"
    source = "Prodes"

    def missing_archive_message(self):
        return "Nenhum arquivo de Prodes foi configurado."

    def load_dataframe(self):
        frames = [self._fetch_layer(workspace, cql) for workspace, cql in PRODES_LAYERS]
        return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4674")

    def _fetch_layer(self, workspace, cql_filter):
        """Baixa a camada `yearly_deforestation` em páginas (ordenadas por
        `fid`, para a paginação do GeoServer ser estável)."""
        session = requests.Session()
        frames, start = [], 0
        while True:
            response = session.get(WFS_URL.format(workspace=workspace), params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": f"{workspace}:yearly_deforestation",
                "CQL_FILTER": cql_filter,
                "propertyName": PROPERTIES,
                "outputFormat": "application/json",
                "srsName": "EPSG:4674",
                "sortBy": "fid",
                "count": PAGE_SIZE,
                "startIndex": start,
            }, timeout=TIMEOUT)
            response.raise_for_status()
            features = response.json().get("features", [])
            if not features:
                break
            # GeoJSON é sempre longitude/latitude, em SIRGAS 2000 (srsName).
            frames.append(gpd.GeoDataFrame.from_features(features, crs="EPSG:4674"))
            if len(features) < PAGE_SIZE:
                break
            start += PAGE_SIZE
        if not frames:
            raise ValueError(f"A API do INPE não retornou dados do PRODES ({workspace}).")
        return pd.concat(frames, ignore_index=True)

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
