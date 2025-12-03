from kernel.service.abstract.base_formatter import BaseFormatter


class SigefFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        details = []
        if getattr(model_obj, "property_code", None):
            details.append(f"Código do imóvel: {model_obj.property_code}")
        if getattr(model_obj, "installment_code", None):
            details.append(f"Parcela: {model_obj.installment_code}")
        if not details and getattr(model_obj, "name", None):
            details.append(f"Nome: {model_obj.name}")
        return {
            "area": intersec["intersection_area_ha"],
            "nome": model_obj.name,
            "status": getattr(model_obj, "status", None),
            "item_info": "Sigef: " + " | ".join(details),
        }
