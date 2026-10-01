import tempfile

import geopandas as gpd
import requests

from environmental_layers.models import IndigenousArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter

# Terras Indígenas da FUNAI, redistribuídas pela ANA (catálogo SNIRH) em
# GeoPackage com link fixo. O GeoServer da FUNAI lista as camadas mas recusa
# o download dos polígonos (403), por isso o arquivo da ANA.
GPKG_URL = "https://metadados.snirh.gov.br/files/3fa8cc38-79b4-4aa1-8179-bba315baea4b/geoft_terra_indigena.gpkg"
TIMEOUT = 300


class IndigenousAreaImporter(BulkShapefileImporter):
    model = IndigenousArea
    archive_field = "indigenous_zip_file"
    source = "Base Indígena"

    def missing_archive_message(self):
        return "Nenhum arquivo de indígena foi configurado."

    def load_dataframe(self):
        response = requests.get(GPKG_URL, timeout=TIMEOUT)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
            tmp.write(response.content)
        df = gpd.read_file(tmp.name)
        # Só as terras do Tocantins (a UF pode vir composta, ex.: "TO,PA").
        return df[df["uf_sigla"].fillna("").str.split(",").apply(lambda ufs: "TO" in ufs)]

    def format_fields(self, row):
        return {
            "indigenous_name": row.get("terrai_nom"),
        }
