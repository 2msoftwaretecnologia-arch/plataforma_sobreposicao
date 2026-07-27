"""
Formatter genérico para bases de dados customizadas (`CustomLayer`). Ao
contrário dos 17 Formatters fixos (`*/services/formatter/*.py`), este não
tem colunas hardcoded — ele lê, em tempo de execução, quais colunas o usuário
marcou como `incluir=True` em `CustomLayerColumn` e monta o resultado a
partir de `CustomLayerFeature.atributos`.
"""

from kernel.service.abstract.base_formatter import BaseFormatter


class CustomLayerFormatter(BaseFormatter):
    def __init__(self, custom_layer):
        self.custom_layer = custom_layer
        self.colunas = list(custom_layer.colunas.filter(incluir=True).order_by('ordem', 'id'))

    def format(self, model_obj, intersec):
        atributos = model_obj.atributos or {}
        data = {
            "area": intersec["intersection_area_ha"],
            "item_info": self._build_item_info(atributos),
            "polygon_wkt": intersec["intersection_geom"].wkt,
            "polygon_geojson": intersec["intersection_geom"].geojson,
        }
        for coluna in self.colunas:
            data[coluna.coluna_origem] = atributos.get(coluna.coluna_origem)
        return data

    def _build_item_info(self, atributos):
        if self.colunas:
            valor = atributos.get(self.colunas[0].coluna_origem)
            if valor not in (None, ""):
                return f"{self.custom_layer.nome}: {valor}"
        return self.custom_layer.nome
