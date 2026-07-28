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
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction

from .models import CustomLayerFeature

SRID = 4674
UTM_SRID = 31982


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

    @staticmethod
    def _apply_geometry(instance, wkt_value):
        try:
            geom = GEOSGeometry(wkt_value, srid=SRID)
            if not geom.valid:
                geom = geom.buffer(0)
            geom.srid = SRID

            geom_utm = geom.transform(UTM_SRID, clone=True)
            instance.usable_geometry = geom
            instance.area_m2 = geom_utm.area
            instance.area_ha = geom_utm.area / 10000
            return True
        except Exception:
            return False

    def execute(self):
        """Importa todas as feições do arquivo, usando as colunas marcadas
        como `incluir=True`. Substitui as feições já existentes desta base
        (mesmo comportamento das bases fixas: reprocessar = recarregar do
        zero), sem afetar as demais bases customizadas.

        Lê o arquivo inteiro e monta as instâncias em memória antes de tocar
        no banco, para não apagar as feições existentes se o arquivo estiver
        ausente/corrompido; a gravação em si é feita com `bulk_create` em vez
        de um INSERT por linha."""
        colunas = list(self.custom_layer.colunas.filter(incluir=True))
        if not colunas:
            raise ValueError("Selecione ao menos uma coluna antes de processar.")

        user = self._get_user()
        df = self._read_file()

        instances = []
        importados = 0
        for _, row in df.iterrows():
            atributos = {c.coluna_origem: _json_safe(row.get(c.coluna_origem)) for c in colunas}
            wkt_value = str(row.get("geometry"))
            instance = CustomLayerFeature(
                layer=self.custom_layer,
                geometry=wkt_value,
                atributos=atributos,
                created_by=user,
                source=self.custom_layer.nome,
            )
            if self._apply_geometry(instance, wkt_value):
                importados += 1
            instances.append(instance)

        with transaction.atomic():
            CustomLayerFeature.objects.filter(layer=self.custom_layer).delete()
            CustomLayerFeature.objects.bulk_create(instances, batch_size=2000)

        return importados
