from kernel.service.abstract.base_formatter import BaseFormatter


class ProtectionAreaFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "unidade": model_obj.unit_name,
            "dominios": model_obj.domains,
            "classe": model_obj.class_group,
            "fundo_legal": model_obj.legal_basis,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }

