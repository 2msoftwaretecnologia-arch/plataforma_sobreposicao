import geopandas as gpd
import pandas as pd

from car_system.models import (
    DeclaredApp,
    DeclaredNativeVegetation,
    DeclaredLegalReserve,
    DeclaredConsolidatedArea,
    DeclaredRestrictedUse,
    DeclaredFallowArea,
    DeclaredAdministrativeEasement,
)
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


def _clean(value):
    return None if value is None or pd.isna(value) else value


class DeclaredThemeImporter(BulkShapefileImporter):
    """Importa um tema do download por estado do SICAR (`TO_<TEMA>.gpkg` ou
    ZIP com o shapefile). Todos os temas têm as mesmas colunas; as
    subclasses só dizem qual Model/arquivo usar."""

    theme_label = None

    def missing_archive_message(self):
        return f"Nenhum arquivo de {self.theme_label} foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        num_area = _clean(row.get("num_area"))
        return {
            "category_source": _clean(row.get("nom_tema")) or self.theme_label,
            "car_number": row.get("cod_imovel"),
            "city": _clean(row.get("municipio")),
            "pending": _clean(row.get("des_condic")),
            "car_status": _clean(row.get("ind_status")),
            "declared_area_ha": float(num_area) if num_area is not None else None,
        }


class DeclaredAppImporter(DeclaredThemeImporter):
    model = DeclaredApp
    archive_field = "declared_app_zip_file"
    source = "Base APP Declarada"
    theme_label = "APP declarada"


class DeclaredNativeVegetationImporter(DeclaredThemeImporter):
    model = DeclaredNativeVegetation
    archive_field = "declared_native_vegetation_zip_file"
    source = "Base Vegetação Nativa Declarada"
    theme_label = "vegetação nativa declarada"


class DeclaredLegalReserveImporter(DeclaredThemeImporter):
    model = DeclaredLegalReserve
    archive_field = "declared_legal_reserve_zip_file"
    source = "Base Reserva Legal Declarada"
    theme_label = "reserva legal declarada"


class DeclaredConsolidatedAreaImporter(DeclaredThemeImporter):
    model = DeclaredConsolidatedArea
    archive_field = "declared_consolidated_area_zip_file"
    source = "Base Área Consolidada Declarada"
    theme_label = "área consolidada declarada"


class DeclaredRestrictedUseImporter(DeclaredThemeImporter):
    model = DeclaredRestrictedUse
    archive_field = "declared_restricted_use_zip_file"
    source = "Base Uso Restrito Declarado"
    theme_label = "área de uso restrito declarada"


class DeclaredFallowAreaImporter(DeclaredThemeImporter):
    model = DeclaredFallowArea
    archive_field = "declared_fallow_area_zip_file"
    source = "Base Área de Pousio Declarada"
    theme_label = "área de pousio declarada"


class DeclaredAdministrativeEasementImporter(DeclaredThemeImporter):
    model = DeclaredAdministrativeEasement
    archive_field = "declared_administrative_easement_zip_file"
    source = "Base Servidão Administrativa Declarada"
    theme_label = "servidão administrativa declarada"
