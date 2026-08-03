"""
Registro operacional das camadas de SHP: liga cada 'modelo' (mesma chave usada
em `bases_config.BASES_CONFIG`) à classe do Model e à classe Importer usada
para (re)processar o arquivo enviado.

Usado pelas views de upload/processar/excluir do painel "Bases de Dados",
para não repetir em cada view qual Importer/Model pertence a qual camada.
"""

from car_system.models import SicarRecord, DeclaredHydrography
from car_system.tasks.sicar_importer import SicarImporter
from car_system.tasks.hydrography_importer import HydrographyImporter

from environmental_layers.models import (
    ZoningArea,
    PhytoecologyArea,
    EnvironmentalProtectionArea,
    IndigenousArea,
)
from environmental_layers.tasks.zoning_importer import ZoningAreaImporter
from environmental_layers.tasks.phytoecology_importer import PhytoecologyAreaImporter
from environmental_layers.tasks.protection_area_importer import EnvironmentalProtectionAreaImporter
from environmental_layers.tasks.indigenous_area_importer import IndigenousAreaImporter

from naturatins.models import Quilombolas, Paths, ConservationUnits, MunicipalBoundaries
from naturatins.tasks.quilombolas_importer import QuilombolasImporter
from naturatins.tasks.paths_importer import PathsImporter
from naturatins.tasks.conservation_units_importer import ConservationUnitsImporter
from naturatins.tasks.municipal_boundaries_importer import MunicipalBoundariesImporter

from gov.models import Sigef, Ruralsettlement, SnicTotal
from gov.tasks.sigef_importer import SigefImporter
from gov.tasks.ruralsettlement_importer import RuralsettlementImporter
from gov.tasks.snic_total_importer import SnicTotalImporter

from deforestation_fires.models import DeforestationMapbiomas, Embargoes, Prodes
from deforestation_fires.tasks.deforestation_mapbiomas_importer import DeforestationMapbiomasImporter
from deforestation_fires.tasks.embargoe_importer import EmbargoesImporter
from deforestation_fires.tasks.prodes_importer import ProdesImporter

from seplan.models import Highways, Ipuca
from seplan.tasks.Highways_importer import HighwaysImporter
from seplan.tasks.ipuca_importer import IpucaImporter


LAYER_REGISTRY = {
    "ZoningArea": {"model": ZoningArea, "importer": ZoningAreaImporter},
    "PhytoecologyArea": {"model": PhytoecologyArea, "importer": PhytoecologyAreaImporter},
    "EnvironmentalProtectionArea": {"model": EnvironmentalProtectionArea, "importer": EnvironmentalProtectionAreaImporter},
    "IndigenousArea": {"model": IndigenousArea, "importer": IndigenousAreaImporter},
    "SicarRecord": {"model": SicarRecord, "importer": SicarImporter},
    "DeclaredHydrography": {"model": DeclaredHydrography, "importer": HydrographyImporter},
    "Quilombolas": {"model": Quilombolas, "importer": QuilombolasImporter},
    "Paths": {"model": Paths, "importer": PathsImporter},
    "ConservationUnits": {"model": ConservationUnits, "importer": ConservationUnitsImporter},
    "MunicipalBoundaries": {"model": MunicipalBoundaries, "importer": MunicipalBoundariesImporter},
    "Sigef": {"model": Sigef, "importer": SigefImporter},
    "Ruralsettlement": {"model": Ruralsettlement, "importer": RuralsettlementImporter},
    "SnicTotal": {"model": SnicTotal, "importer": SnicTotalImporter},
    "DeforestationMapbiomas": {"model": DeforestationMapbiomas, "importer": DeforestationMapbiomasImporter},
    "Embargoes": {"model": Embargoes, "importer": EmbargoesImporter},
    "Prodes": {"model": Prodes, "importer": ProdesImporter},
    "Highways": {"model": Highways, "importer": HighwaysImporter},
    "Ipuca": {"model": Ipuca, "importer": IpucaImporter},
}
