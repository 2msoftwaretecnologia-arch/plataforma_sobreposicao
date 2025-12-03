from kernel.service.abstract.base_formatter import BaseFormatter


class SigefFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.name,
            "status": getattr(model_obj, "status", None),
            "item_info": "Sigef: {}".format(model_obj.property_code if hasattr(model_obj, "property_code") else model_obj.name),
        }
