from environmental_layers.models import EnvironmentalProtectionArea


class ProtectionAreaLoader:
    
    @staticmethod
    def load_protection_area_data():
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
