from kernel.service.abstract.base_formatter import BaseFormatter


class PhytoecologyFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.phyto_name,
            "item_info": "Regioões FitoEcologicas: {}".format(model_obj.phyto_name)
        }
