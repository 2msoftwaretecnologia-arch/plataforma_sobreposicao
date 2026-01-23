from typing import Dict
from django.db import models
from kernel.service.abstract.base_formatter import BaseFormatter
from deforestation_fires.utils import build_mapbiomas_url


class DeforestationMapbiomasFormatter(BaseFormatter):
    def format(self, model_obj: models.Model, intersec: Dict) -> Dict:
        nome = f"Alerta {model_obj.alert_code}" if getattr(model_obj, "alert_code", None) else "Alerta"
        try:
            detection_year = int(float(model_obj.detection_year))
        except (ValueError, TypeError):
            detection_year = model_obj.detection_year

        item_info = f"MapBiomas: Alerta {model_obj.alert_code} | Ano: {detection_year}"
        return {
            "area": intersec["intersection_area_ha"],
            "nome": nome,
            "item_info": item_info,
            "alert_code": model_obj.alert_code,
            "detection_year": detection_year,
            "source": model_obj.source,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
            "mapbiomas_url": build_mapbiomas_url(model_obj.alert_code),
        }
