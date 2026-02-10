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

class FormatterRegister:
    
    def __init__(self):
        self._formatters = {
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
        
    @property
    def formatters(self):
        return self._formatters
