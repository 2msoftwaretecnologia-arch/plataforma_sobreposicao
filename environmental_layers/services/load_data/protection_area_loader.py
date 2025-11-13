from typing import Dict, Any, List
from environmental_layers.models import EnvironmentalProtectionArea


class ProtectionAreaLoader:
    
    @staticmethod
    def load() -> List[Dict[str, Any]:]:
        protection_areas = EnvironmentalProtectionArea.objects.all()
        protection_area_data = []
        
        for area in protection_areas:
            protection_area_data.append({
                'wkt': area.geometry,
                'unidade': area.unit_name,
                'dominios': area.domains,
                'classe': area.class_group,
                'fundo_legal': area.legal_basis
            })
        
        return protection_area_data
