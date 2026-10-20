from kernel.service.abstract.base_formatter import BaseFormatter


class CarEstadual2023Formatter(BaseFormatter):
    def format(self, model_obj, intersec):
        details = [f"Nº {model_obj.car_number}"]
        if model_obj.property_name:
            details.append(model_obj.property_name)

        return {
            "area": intersec["intersection_area_ha"],
            "item_info": "CAR Estadual 13/02/2023 - " + " | ".join(details),
            "numero_car": model_obj.car_number,
            "nome_imovel": model_obj.property_name,
            "status": model_obj.status,
            "car_federal": model_obj.federal_car_number,
            "municipio": model_obj.city,
            "cod_ibge": model_obj.ibge_code,
            "area_declarada_ha": model_obj.declared_area_ha,
            "modulos_fiscais": model_obj.fiscal_modules,
            "data_cadastro": model_obj.registration_date.strftime("%d/%m/%Y") if model_obj.registration_date else None,
            "email_contato": model_obj.contact_email,
            "telefone_contato": model_obj.contact_phone,
            "cadastrante": model_obj.registrant_name,
            "tipo_area": model_obj.area_type,
            "proprietario": model_obj.information,
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
