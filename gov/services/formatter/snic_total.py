from kernel.service.abstract.base_formatter import BaseFormatter


class SnicTotalFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.property_name,
            "item_info": f"Imóvel: {model_obj.property_name} | Código do imóvel: {model_obj.property_code}"
        }
