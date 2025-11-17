# services/search/processor_registry.py
from car_system.services.process_data.sicar_process import SicarProcess
from car_system.services.read_files.sicar_loader import SicarRecordLoader
from environmental_layers.services.load_data.zoning_loader import ZoningLoader
from environmental_layers.services.precess_data.phytoecology_process import PhytoecologyProcess
from environmental_layers.services.precess_data.protection_area_process import ProtectionAreaProcess
from environmental_layers.services.precess_data.zoning_loader_process import ZoningProcess
from environmental_layers.services.load_data.phytoecology_loader import PhytoecologyLoader
from environmental_layers.services.load_data.protection_area_loader import ProtectionAreaLoader



class ProcessorRegistry:
    """Registra os processadores associados aos loaders."""
    
    def __init__(self, verifier):
        self._registry = {
            SicarRecordLoader: SicarProcess(verifier),
            ZoningLoader: ZoningProcess(verifier),
            PhytoecologyLoader: PhytoecologyProcess(verifier),
            ProtectionAreaLoader: ProtectionAreaProcess(verifier),
        }

    @property
    def processors(self):
        return self._registry
