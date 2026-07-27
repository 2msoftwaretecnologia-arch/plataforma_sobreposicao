"""
Importer genérico para bases de dados customizadas (`CustomLayer`): descobre
as colunas de um shapefile enviado pelo painel e, depois que o usuário
escolhe quais quer manter (`CustomLayerColumn`), importa as feições para a
tabela compartilhada `CustomLayerFeature`.

Espelha o padrão dos importers fixos (`*/tasks/*_importer.py`), mas em vez de
mapear colunas para campos de Model fixos, guarda os valores escolhidos em
`atributos` (JSONField).
"""

import geopandas as gpd
from django.contrib.auth.models import User

from kernel.service.geometry_processing_service import GeometryProcessingService

from .models import CustomLayerFeature


def _json_safe(value):
    """Converte tipos do pandas/numpy (int64, Timestamp, ...) para tipos
    nativos do Python antes de guardar em um JSONField."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return str(value)


class CustomLayerImporter:
    def __init__(self, custom_layer, user=None):
        self.custom_layer = custom_layer
        self.user = user

    def _get_user(self):
        if self.user:
            return self.user
        user = User.objects.first()
        if not user:
            raise ValueError("Nenhum usuário encontrado.")
        return user

    def _read_file(self, **kwargs):
        if not self.custom_layer.arquivo:
            raise ValueError(f"Nenhum arquivo enviado para \"{self.custom_layer.nome}\".")
        return gpd.read_file(self.custom_layer.arquivo.path, **kwargs)

    def discover_columns(self):
        """Lê só as colunas disponíveis no shapefile enviado (não importa nada)."""
        df = self._read_file(rows=1)
        return [c for c in df.columns if c != "geometry"]

    def execute(self):
        """Importa todas as feições do arquivo, usando as colunas marcadas
        como `incluir=True`. Substitui as feições já existentes desta base
        (mesmo comportamento das bases fixas: reprocessar = recarregar do
        zero), sem afetar as demais bases customizadas."""
        colunas = list(self.custom_layer.colunas.filter(incluir=True))
        if not colunas:
            raise ValueError("Selecione ao menos uma coluna antes de processar.")

        user = self._get_user()
        df = self._read_file()

        CustomLayerFeature.objects.filter(layer=self.custom_layer).delete()

        importados = 0
        for _, row in df.iterrows():
            atributos = {c.coluna_origem: _json_safe(row.get(c.coluna_origem)) for c in colunas}
            obj = CustomLayerFeature.objects.create(
                layer=self.custom_layer,
                geometry=str(row.get("geometry")),
                atributos=atributos,
                created_by=user,
                source=self.custom_layer.nome,
            )
            if GeometryProcessingService(CustomLayerFeature).process_instance(obj):
                importados += 1

        return importados
