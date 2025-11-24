from kernel.service.abstract.base_formatter import BaseFormatter


class SnicTotalFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.property_name,
            "item_info": "Código do imovel: {}".format(model_obj.property_code)
        }
