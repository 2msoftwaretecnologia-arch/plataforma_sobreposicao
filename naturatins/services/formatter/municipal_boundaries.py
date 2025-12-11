from kernel.service.abstract.base_formatter import BaseFormatter


class MunicipalBoundariesFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "name": model_obj.name,
            "item_info": "Município: {}".format(model_obj.name),
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
