from kernel.service.abstract.base_formatter import BaseFormatter


class ProtectionAreaFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        details = []
        if getattr(model_obj, "unit_name", None):
            details.append(str(model_obj.unit_name))
        if getattr(model_obj, "domains", None):
            details.append(f"Domínios: {model_obj.domains}")
        if getattr(model_obj, "class_group", None):
            details.append(f"Classe: {model_obj.class_group}")
        if getattr(model_obj, "legal_basis", None):
            details.append(f"Fundo Legal: {model_obj.legal_basis}")

        item_info = "APA: " + " | ".join(details) if details else "APA"

        return {
            "area": intersec["intersection_area_ha"],
            "unidade": model_obj.unit_name,
            "dominios": model_obj.domains,
            "classe": model_obj.class_group,
            "fundo_legal": model_obj.legal_basis,
            "item_info": item_info,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }

