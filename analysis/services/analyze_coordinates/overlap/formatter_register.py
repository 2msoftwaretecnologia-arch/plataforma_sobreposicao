from car_system.models import SicarRecord
from car_system.services.formatter.sicar_formatter import SicarFormatter
from environmental_layers.models import ZoningArea, PhytoecologyArea, EnvironmentalProtectionArea, IndigenousArea
from environmental_layers.services.formatter.phytoecology_formatter import PhytoecologyFormatter
from environmental_layers.services.formatter.zone_formatter import ZoningFormatter
from environmental_layers.services.formatter.indigenous_formatter import IndigenousFormatter
from environmental_layers.services.formatter.protection_area_formatter import ProtectionAreaFormatter

class FormatterRegister:
    
    def __init__(self):
        self._formatters = {
            ZoningArea: ZoningFormatter(),
            PhytoecologyArea: PhytoecologyFormatter(),
            EnvironmentalProtectionArea: ProtectionAreaFormatter(),
            IndigenousArea: IndigenousFormatter(),
            SicarRecord: SicarFormatter(),
        }
        
    @property
    def formatters(self):
        return self._formatters