from environmental_layers.models import PhytoecologyArea


class PhytoecologyLoader:
    
    @staticmethod
    def load_phytoecology_data():
        phytoecology_areas = PhytoecologyArea.objects.all()
        phytoecology_data = []
        
        for phyto in phytoecology_areas:
            phytoecology_data.append({
                'wkt': phyto.geometry,
                'nome_fitoecologia': phyto.phyto_name
            })
        
        return phytoecology_data
