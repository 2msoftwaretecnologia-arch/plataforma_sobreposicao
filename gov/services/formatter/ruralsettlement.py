from kernel.service.abstract.base_formatter import BaseFormatter


class RuralsettlementFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.project_name,
            "item_info": "Método de obtenção: {}".format(model_obj.method_obtaining)
        }
