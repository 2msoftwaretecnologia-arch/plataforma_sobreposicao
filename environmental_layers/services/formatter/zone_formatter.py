from kernel.service.abstract.base_formatter import BaseFormatter


class ZoningFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "zona": model_obj.zone_name,
            "sigla": model_obj.zone_acronym,
            "item_info": f"Zonemaento: {model_obj.zone_name} ({model_obj.zone_acronym})",
        }
