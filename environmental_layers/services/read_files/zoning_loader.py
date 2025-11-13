from environmental_layers.models import ZoningArea

class ZoningLoader:
    
    @staticmethod
    def load_zoning_area_data():
        zoning_areas = ZoningArea.objects.all()
        zoning_data = []

        for zone in zoning_areas:
            zoning_data.append({
                'wkt': zone.geometry,
                'nome_zona': zone.zone_name,
                'sigla_zona': zone.zone_acronym
            })
        
        return zoning_data
