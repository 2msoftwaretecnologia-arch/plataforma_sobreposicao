from kernel.service.abstract.base_formatter import BaseFormatter


class DeclaredThemeFormatter(BaseFormatter):
    """Formatter comum aos temas declarados no CAR (APP, vegetação nativa,
    reserva legal...). Não devolve `status`: o template de resultados usa
    essa chave para reconhecer o perímetro do imóvel SICAR."""

    def __init__(self, label):
        self.label = label

    def format(self, model_obj, intersec):
        details = [f"CAR: {model_obj.car_number}"]
        if model_obj.pending:
            details.append(f"Condição: {model_obj.pending}")

        return {
            "area": intersec["intersection_area_ha"],
            "item_info": f"{self.label} ({model_obj.category_source}) - " + " | ".join(details),
            "categoria": model_obj.category_source,
            "pendencia": model_obj.pending,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
