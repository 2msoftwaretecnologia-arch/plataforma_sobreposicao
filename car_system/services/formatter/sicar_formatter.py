from kernel.service.abstract.base_formatter import BaseFormatter

class SicarFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        status_map = {
            "at": "ativo",
            "ca": "cancelado",
            "pe": "pendente",
            "su": "suspenso",
        }

        raw_status = (model_obj.status or "").strip().lower()
        label_status = status_map.get(raw_status, model_obj.status)

        return {
            "area": intersec["intersection_area_ha"],
            "item_info": f"Sicar - CAR: {model_obj.car_number}",
            "status": label_status,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
