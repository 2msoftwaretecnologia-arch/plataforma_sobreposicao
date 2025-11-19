from kernel.service.abstract.base_formatter import BaseFormatter

class SicarFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "item_info": f"Sicar - CAR: {model_obj.car_number}",
            "status": model_obj.status,
        }