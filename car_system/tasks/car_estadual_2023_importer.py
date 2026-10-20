import geopandas as gpd
import pandas as pd

from car_system.models import CarEstadual2023
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


def _clean(value):
    return None if value is None or pd.isna(value) else value


class CarEstadual2023Importer(BulkShapefileImporter):
    model = CarEstadual2023
    archive_field = "car_estadual_2023_zip_file"
    source = "Base CAR Estadual 13/02/2023"

    def missing_archive_message(self):
        return "Nenhum arquivo do CAR Estadual (13/02/2023) foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        cod_ibge = _clean(row.get("cod_ibge"))
        cadastro = _clean(row.get("cadastro"))
        return {
            "car_number": str(row.get("numero_car")),
            "federal_car_number": _clean(row.get("carfederal")),
            "property_name": _clean(row.get("nom_imovel")),
            "status": _clean(row.get("status")),
            "city": _clean(row.get("municipio")),
            "ibge_code": int(cod_ibge) if cod_ibge is not None else None,
            "declared_area_ha": _clean(row.get("ha_imovel")),
            "fiscal_modules": _clean(row.get("mf_imovel")),
            "registration_date": pd.Timestamp(cadastro).date() if cadastro is not None else None,
            "contact_email": _clean(row.get("email_cont")),
            "contact_phone": _clean(row.get("telefone_c")),
            "registrant_name": _clean(row.get("nome_cadas")),
            "area_type": _clean(row.get("tipo_area")),
            "information": _clean(row.get("informacoe")),
        }
