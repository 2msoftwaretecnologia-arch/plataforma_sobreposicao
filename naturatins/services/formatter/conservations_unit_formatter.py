from kernel.service.abstract.base_formatter import BaseFormatter


class ConservationUnitsFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "unit": model_obj.unit,
            "domain": model_obj.domain,
            "item_info": "Unidades de Conservação: {} - {}".format(model_obj.unit, model_obj.domain),
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
