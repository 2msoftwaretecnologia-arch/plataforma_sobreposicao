import geopandas as gpd

from seplan.models import Highways
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter

UTM_SRID = 31982  # SIRGAS 2000 / UTM 22S: buffer em metros

# Rodovias vêm como linhas, e a análise mede ÁREA de sobreposição (linha
# teria 0 ha e seria sempre descartada). Por isso cada trecho vira a sua
# faixa de domínio: largura TOTAL em metros, por jurisdição (`Juris`).
FAIXA_DOMINIO_M = {
    "federal": 60,
    "estadual": 60,
}
FAIXA_DOMINIO_PADRAO_M = 30  # municipais, urbanas, vicinais, privadas


def faixa_dominio_m(jurisdicao):
    return FAIXA_DOMINIO_M.get(str(jurisdicao or "").strip().lower(), FAIXA_DOMINIO_PADRAO_M)


class HighwaysImporter(BulkShapefileImporter):
    model = Highways
    archive_field = "highways_zip_file"
    source = "Base Highways"

    def missing_archive_message(self):
        return "Nenhum arquivo de highways foi configurado."

    def read_dataframe(self, path):
        try:
            df = gpd.read_file(path, encoding="utf-8")
        except UnicodeDecodeError:
            df = gpd.read_file(path, encoding="latin1")
        df = df[df.geometry.notna() & ~df.geometry.is_empty]
        larguras = df["Juris"].map(faixa_dominio_m) if "Juris" in df else FAIXA_DOMINIO_PADRAO_M
        faixas = df.geometry.to_crs(epsg=UTM_SRID).buffer(larguras / 2)
        return df.set_geometry(faixas.to_crs(df.crs))

    def format_fields(self, row):
        # Rodovias_2018 (SEPLAN-TO): `NmNomeVia` = BR-153, TO-010...;
        # `Class2018` = Pavimentada, Leito Natural... Os campos do Model
        # mantêm o nome antigo (NOME_2011/CLAS_2011).
        return {
            "NOME_2011": row.get("NmNomeVia") or row.get("Nome2018") or row.get("NOME_2011") or "Sem Nome",
            "CLAS_2011": row.get("Class2018") or row.get("Legenda") or row.get("CLAS_2011") or "Sem Classe",
        }
