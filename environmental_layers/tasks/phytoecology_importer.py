import geopandas as gpd

from environmental_layers.models import PhytoecologyArea
from kernel.service.bulk_shapefile_importer import BulkShapefileImporter


class PhytoecologyAreaImporter(BulkShapefileImporter):
    model = PhytoecologyArea
    archive_field = "phytoecology_zip_file"
    source = "Base Fitoecologia"

    def missing_archive_message(self):
        return "Nenhum arquivo de fitoecologia foi configurado."

    def read_dataframe(self, path):
        return gpd.read_file(path, encoding="utf-8")

    def format_fields(self, row):
        # Regiões fitoecológicas do IBGE (TO): `NM_UVEG` é a vegetação; onde
        # ela não existe mais vem o uso antrópico (`NM_UANTR`, ex.:
        # pastagem) e, nos corpos d'água, nenhum dos dois. `AnáliseCA` é a
        # classe da Reserva Legal (Cerrado 35%, Floresta 80%...).
        phyto_type = _text(row.get("AnáliseCA"))
        return {
            "phyto_name": _text(row.get("NM_UVEG")) or _text(row.get("NM_UANTR")) or phyto_type,
            "phyto_type": phyto_type,
        }


def _text(value):
    return value.strip() if isinstance(value, str) else ""
