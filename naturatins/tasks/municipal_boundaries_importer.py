import geopandas as gpd

from naturatins.models import MunicipalBoundaries
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class MunicipalBoundariesImporter(BulkShapefileImporter):
    model = MunicipalBoundaries
    archive_field = "municipal_boundaries_zip_file"
    source = "Base Municípios"

    def missing_archive_message(self):
        return "Nenhum arquivo de municípios foi configurado."

    def read_dataframe(self, path):
        # A malha do IBGE (TO_Municipios_2024) vem em Latin-1.
        try:
            return gpd.read_file(path, encoding="utf-8")
        except UnicodeDecodeError:
            return gpd.read_file(path, encoding="latin1")

    def format_fields(self, row):
        return {
            # `NM_MUN` na malha municipal do IBGE; `NOME` em arquivos antigos.
            "name": row.get("NM_MUN") or row.get("NOME"),
        }
