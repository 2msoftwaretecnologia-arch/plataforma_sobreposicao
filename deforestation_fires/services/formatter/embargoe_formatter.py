from kernel.service.abstract.base_formatter import BaseFormatter


class EmbargoeFormatter(BaseFormatter):
    def format(self, model_obj, intersec):
        return {
            "area": intersec["intersection_area_ha"],
            "property_name": model_obj.property_name,
            "type_area": model_obj.type_area,
            "number_infraction_act": model_obj.number_infraction_act,
            "nome_embargado": model_obj.nome_embargado,
            "cpf_cnpj_embargado": model_obj.cpf_cnpj_embargado,
            "control_unity": model_obj.control_unity,
            "process_number": model_obj.process_number,
            "act_description": model_obj.act_description,
            "infraction_description": model_obj.infraction_description,
            "embargoe_date": model_obj.embargoe_date,
            "priting_date": model_obj.priting_date,
            "item_info": f"Embargoe: {model_obj.number_infraction_act}",
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
