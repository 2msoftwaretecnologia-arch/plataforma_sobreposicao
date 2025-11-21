from kernel.service.abstract.base_formatter import BaseFormatter


class QuilombolasFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.name,
            "item_info": "Quilombolas: {}".format(model_obj.name)
        }
