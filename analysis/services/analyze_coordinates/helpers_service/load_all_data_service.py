from typing import Any, Dict, List

from car_system.services.read_files.sicar_loader import SicarRecordLoader
from environmental_layers.services.load_data.phytoecology_loader import PhytoecologyLoader
from environmental_layers.services.load_data.protection_area_loader import ProtectionAreaLoader
from environmental_layers.services.load_data.zoning_loader import ZoningLoader


class LoadAllDataService:
    """Serviço para carregar todos os dados necessários para análise de sobreposição."""

    @staticmethod
    def load_all(car=None) -> List[Dict[str, Any]]:
        """Carrega dados de todas as bases necessárias para a análise de sobreposição.

        Args:
            car (Optional[Car]): Instância opcional de Car para carregamento condicional.

        Returns:
            Dict[str, List[Dict[str, Any]]]: Dicionário com listas de registros de cada base.
        """
        properties_data = SicarRecordLoader.load(car=car)
        zoning_data = ZoningLoader.load()
        phyto_data = PhytoecologyLoader.load()
        protection_area_data = ProtectionAreaLoader.load()

        pipeline = [
            {
                "loader": SicarRecordLoader,
                "base_name": "Base de Dados Sicar",
                "data": properties_data,
            },
            {
                "loader": ZoningLoader,
                "base_name": "Base de Dados de Zoneamento",
                "data": zoning_data,
            },
            {
                "loader": PhytoecologyLoader,
                "base_name": "Base de Dados de Fitoecologias",
                "data": phyto_data,
            },
            {
                "loader": ProtectionAreaLoader,
                "base_name": "Base de Dados de APAs",
                "data": protection_area_data,
            },
        ]

        return pipeline