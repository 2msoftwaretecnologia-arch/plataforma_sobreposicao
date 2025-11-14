from typing import Any, Dict, List

from car_system.services.read_files.sicar_loader import SicarRecordLoader
from environmental_layers.services.load_data.phytoecology_loader import PhytoecologyLoader
from environmental_layers.services.load_data.protection_area_loader import ProtectionAreaLoader
from environmental_layers.services.load_data.zoning_loader import ZoningLoader


class LoadAllDataService:
    """Serviço para carregar todos os dados necessários para análise de sobreposição."""

    def load_all(self, car=None) -> Dict[str, List[Dict[str, Any]]]:
        """Carrega dados de todas as bases necessárias para a análise."""
        properties_data = SicarRecordLoader.load(car=car)
        zoning_data = ZoningLoader.load()
        phyto_data = PhytoecologyLoader.load()
        protection_area_data = ProtectionAreaLoader.load()

        results_by_base = {
            "imoveis": properties_data,
            "zoneamento": zoning_data,
            "fitoecologias": phyto_data,
            "apas": protection_area_data,
        }