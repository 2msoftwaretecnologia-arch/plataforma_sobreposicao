from kernel.service.abstract.base_formatter import BaseFormatter


class HighwaysFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "NOME_2011": model_obj.NOME_2011,
            "CLAS_2011": model_obj.CLAS_2011,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
