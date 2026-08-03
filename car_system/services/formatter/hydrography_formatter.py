from kernel.service.abstract.base_formatter import BaseFormatter


class HydrographyFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        details = [f"CAR: {model_obj.car_number}"]
        if model_obj.pending:
            details.append(f"Pendente: {model_obj.pending}")

        return {
            "area": intersec["intersection_area_ha"],
            "item_info": f"Hidrografia Declarada ({model_obj.category_source}) - " + " | ".join(details),
            "categoria": model_obj.category_source,
            "pendencia": model_obj.pending,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
