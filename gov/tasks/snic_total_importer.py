import geopandas as gpd
import pandas as pd

from gov.models import SnicTotal
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs_gml

# Imóveis certificados pelo SNCI (certificação anterior ao SIGEF), privados e
# públicos, do Tocantins, direto do i3Geo do Acervo Fundiário do INCRA (WFS).
I3GEO_URL = "https://acervofundiario.incra.gov.br/i3geo/ogc.php"
SNCI_LAYERS = ("imoveiscertificados_privado_to", "imoveiscertificados_publico_to")


class SnicTotalImporter(BulkShapefileImporter):
    model = SnicTotal
    archive_field = "snic_total_zip_file"
    source = "Base SnicTotal"

    def missing_archive_message(self):
        return "Nenhum arquivo de SnicTotal foi configurado."

    def load_dataframe(self):
        frames = [
            fetch_wfs_gml(I3GEO_URL, tema, sort_by="id1", extra_params={"tema": tema})
            for tema in SNCI_LAYERS
        ]
        return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

    def format_fields(self, row):
        # Nomes completos na API; abreviados (shapefile) nas versões antigas.
        code = row.get("cod_imovel_rural") or row.get("cod_imovel")
        return {
            "property_name": row.get("nome_imovel") or row.get("nome_imove"),
            "property_code": "" if code is None or pd.isna(code) else str(code),
        }
