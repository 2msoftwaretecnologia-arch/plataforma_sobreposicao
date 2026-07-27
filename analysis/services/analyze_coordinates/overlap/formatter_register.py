from car_system.models import SicarRecord
from car_system.services.formatter.sicar_formatter import SicarFormatter
from environmental_layers.models import (
    ZoningArea,
    PhytoecologyArea,
    EnvironmentalProtectionArea,
    IndigenousArea,
)
from environmental_layers.services.formatter.phytoecology_formatter import PhytoecologyFormatter
from environmental_layers.services.formatter.zone_formatter import ZoningFormatter
from environmental_layers.services.formatter.indigenous_formatter import IndigenousFormatter
from environmental_layers.services.formatter.protection_area_formatter import ProtectionAreaFormatter
from naturatins.models import Quilombolas, Paths, ConservationUnits, MunicipalBoundaries
from naturatins.services.formatter.quilobolas_formatter import QuilombolasFormatter
from naturatins.services.formatter.paths_formatter import PathsFormatter
from naturatins.services.formatter.conservations_unit_formatter import ConservationUnitsFormatter
from naturatins.services.formatter.municipal_boundaries import MunicipalBoundariesFormatter
from gov.models import Sigef, Ruralsettlement, SnicTotal
from gov.services.formatter.ruralsettlement import RuralsettlementFormatter
from gov.services.formatter.snic_total import SnicTotalFormatter
from gov.services.formatter.sigef_formatter import SigefFormatter
from deforestation_fires.models import DeforestationMapbiomas, Embargoes, Prodes
from deforestation_fires.services.formatter.deforestation_mabBiomas_formatter import DeforestationMapbiomasFormatter
from deforestation_fires.services.formatter.embargoe_formatter import EmbargoeFormatter
from deforestation_fires.services.formatter.prodes_formatter import ProdesFormatter
from seplan.models import Ipuca, Highways
from seplan.services.formatter.ipuca import IpucaFormatter
from seplan.services.formatter.Highways import HighwaysFormatter

from control_panel.column_toggle_service import get_disabled_fields_map
from control_panel.custom_layer_formatter import CustomLayerFormatter
from control_panel.custom_layer_proxy import build_active_layer_proxies

# Chaves estruturais do resultado: sempre presentes, nunca podem ser
# desligadas pelo painel de "Colunas do Resultado da Análise" (área/geometria
# alimentam o cálculo de sobreposição; item_info é o rótulo exibido; as
# demais são valores derivados usados em outro lugar do pipeline).
PROTECTED_FORMATTER_KEYS = {
    "area", "item_info", "polygon_wkt", "polygon_geojson",
    "preserved_area", "mapbiomas_url",
}


class _ColumnFilteredFormatter:
    """Envolve um Formatter existente e remove, do dicionário devolvido,
    as colunas que o usuário desligou em `LayerFieldToggle` — sem alterar o
    Formatter original."""

    def __init__(self, inner_formatter, disabled_fields):
        self._inner = inner_formatter
        self._disabled = disabled_fields

    def format(self, model_obj, intersec):
        data = self._inner.format(model_obj, intersec)
        if not self._disabled:
            return data
        return {
            key: value for key, value in data.items()
            if key in PROTECTED_FORMATTER_KEYS or key not in self._disabled
        }


class FormatterRegister:

    def __init__(self):
        raw_formatters = {
            ZoningArea: ZoningFormatter(),
            PhytoecologyArea: PhytoecologyFormatter(),
            EnvironmentalProtectionArea: ProtectionAreaFormatter(),
            IndigenousArea: IndigenousFormatter(),
            SicarRecord: SicarFormatter(),
            Quilombolas: QuilombolasFormatter(),
            Paths: PathsFormatter(),
            ConservationUnits: ConservationUnitsFormatter(),
            MunicipalBoundaries: MunicipalBoundariesFormatter(),
            Sigef: SigefFormatter(),
            Ruralsettlement: RuralsettlementFormatter(),
            SnicTotal: SnicTotalFormatter(),
            DeforestationMapbiomas: DeforestationMapbiomasFormatter(),
            Embargoes: EmbargoeFormatter(),
            Prodes: ProdesFormatter(),
            Ipuca: IpucaFormatter(),
            Highways: HighwaysFormatter(),
        }

        disabled_map = get_disabled_fields_map()
        self._formatters = {
            model: _ColumnFilteredFormatter(formatter, disabled_map.get(model.__name__, set()))
            for model, formatter in raw_formatters.items()
        }

        # Bases customizadas (criadas pelo painel, sem Model/Formatter fixos)
        # que o usuário já ativou explicitamente após revisar os dados importados.
        for proxy, custom_layer in build_active_layer_proxies():
            self._formatters[proxy] = CustomLayerFormatter(custom_layer)

    @property
    def formatters(self):
        return self._formatters
