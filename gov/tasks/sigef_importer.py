import geopandas as gpd
import pandas as pd

from gov.models import Sigef
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter
from kernel.service.wfs import fetch_wfs_gml

# Imóveis certificados no SIGEF (particulares e públicos) do Tocantins,
# direto do i3Geo do Acervo Fundiário do INCRA (WFS), sem shapefile.
I3GEO_URL = "https://acervofundiario.incra.gov.br/i3geo/ogc.php"
SIGEF_LAYERS = ("certificada_sigef_particular_to", "certificada_sigef_publico_to")


class SigefImporter(BulkShapefileImporter):
    model = Sigef
    archive_field = "sigef_zip_file"
    source = "Base Sigef"

    def missing_archive_message(self):
        return "Nenhum arquivo de sigef foi configurado."

    def load_dataframe(self):
        frames = [
            fetch_wfs_gml(I3GEO_URL, tema, sort_by="id", extra_params={"tema": tema})
            for tema in SIGEF_LAYERS
        ]
        return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

    def natural_key(self, row):
        return row.get("parcela_codigo")

    def format_fields(self, row):
        return {
            "name": _text(row.get("nome_area")) or "Sem Nome",
            "installment_code": _text(row.get("parcela_codigo")) or "Sem Parcela",
            "property_code": _text(row.get("codigo_imovel")) or "Sem Propriedade",
            "status": _text(row.get("status")) or "Sem Status",
        }


def _text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()
