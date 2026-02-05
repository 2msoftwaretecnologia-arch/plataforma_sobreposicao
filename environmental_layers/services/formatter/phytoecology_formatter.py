from kernel.service.abstract.base_formatter import BaseFormatter
from environmental_layers.constants import PHYTOECOLOGY_PERCENTAGE

class PhytoecologyFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        preserved_area = intersec.get("intersection_area_ha", 0) * (
            PHYTOECOLOGY_PERCENTAGE.get(model_obj.phyto_name, 0) / 100
        )

        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.phyto_name,
            "item_info": "{}".format(model_obj.phyto_name),
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
            "preserved_area": preserved_area
        }
