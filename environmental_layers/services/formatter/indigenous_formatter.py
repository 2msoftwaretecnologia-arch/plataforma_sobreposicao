from kernel.service.abstract.base_formatter import BaseFormatter


class IndigenousFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "nome_area": model_obj.indigenous_name,
            "item_info": "Áreas de Proteção Ambiental: {}".format(model_obj.indigenous_name),
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
