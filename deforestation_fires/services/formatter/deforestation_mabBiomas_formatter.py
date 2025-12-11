from kernel.service.abstract.base_formatter import BaseFormatter


class DeforestationMapbiomasFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        nome = f"Alerta {model_obj.alert_code}" if getattr(model_obj, "alert_code", None) else "Alerta"
        item_info = f"MapBiomas: Alerta {model_obj.alert_code} | Ano: {model_obj.detection_year}"
        return {
            "area": intersec["intersection_area_ha"],
            "nome": nome,
            "item_info": item_info,
            "alert_code": model_obj.alert_code,
            "detection_year": model_obj.detection_year,
            "source": model_obj.source,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
