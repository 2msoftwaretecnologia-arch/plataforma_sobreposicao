from kernel.service.abstract.base_formatter import BaseFormatter


class DeforestationMapbiomasFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "alert_code": model_obj.alert_code,
            "detection_year": model_obj.detection_year,
            "source": model_obj.source,
        }
