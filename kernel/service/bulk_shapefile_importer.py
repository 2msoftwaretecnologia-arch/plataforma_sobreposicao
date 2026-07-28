import geopandas as gpd
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction

from control_panel.utils import get_file_management
from kernel.utils import reset_db

SRID = 4674
UTM_SRID = 31982


class BulkShapefileImporter:
    """
    Importador genérico para as bases fixas de SHP (SICAR, Zoneamento, APAs,
    Fitoecologia, etc.).

    Lê o arquivo inteiro com geopandas, monta todas as instâncias do Model em
    memória (já com `usable_geometry`/`area_m2`/`area_ha` calculados) e grava
    tudo em lotes com `bulk_create`, em vez de um INSERT + SELECT de dedup por
    linha — para uma base com dezenas/centenas de milhares de registros isso é
    a diferença entre segundos e horas.

    `reset_db` só é chamado depois que o arquivo foi lido e as instâncias
    montadas com sucesso, para não truncar a tabela existente quando o
    arquivo enviado está ausente/corrompido. Reprocessar sempre recarrega a
    base do zero — por isso não há checagem de duplicados contra o banco.
    """

    model = None
    archive_field = None
    source = None
    batch_size = 2000

    def __init__(self, user=None):
        self.user = user

    def _get_user(self):
        if self.user:
            return self.user
        user = User.objects.first()
        if not user:
            raise ValueError("Nenhum usuário encontrado.")
        return user

    def missing_archive_message(self):
        return "Nenhum arquivo foi configurado."

    def format_fields(self, row):
        """Retorna um dict dos campos específicos do Model (exceto geometry/created_by/source)."""
        raise NotImplementedError

    def natural_key(self, row):
        """Chave opcional usada para descartar duplicados dentro do próprio
        arquivo antes do bulk_create (necessário só quando o Model tem uma
        constraint unique nos campos importados, ex.: SicarRecord.car_number)."""
        return None

    def read_dataframe(self, path):
        return gpd.read_file(path)

    def _apply_geometry(self, instance, wkt_value):
        try:
            geom = GEOSGeometry(wkt_value, srid=SRID)
            if not geom.valid:
                geom = geom.buffer(0)
            geom.srid = SRID

            geom_utm = geom.transform(UTM_SRID, clone=True)
            instance.usable_geometry = geom
            instance.area_m2 = geom_utm.area
            instance.area_ha = geom_utm.area / 10000
        except Exception:
            pass

    def _build_instance(self, row, user):
        wkt_value = str(row.get("geometry"))
        fields = self.format_fields(row)
        instance = self.model(
            **fields,
            geometry=wkt_value,
            created_by=user,
            source=self.source,
        )
        self._apply_geometry(instance, wkt_value)
        return instance

    def _get_archive_path(self):
        file_mgmt = get_file_management()
        file_field = getattr(file_mgmt, self.archive_field, None) if file_mgmt else None
        if not file_field or not file_field.name:
            raise ValueError(self.missing_archive_message())
        return file_field.path

    def execute(self):
        user = self._get_user()
        path = self._get_archive_path()
        df = self.read_dataframe(path)

        instances = []
        seen_keys = set()
        for _, row in df.iterrows():
            key = self.natural_key(row)
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            instances.append(self._build_instance(row, user))

        reset_db(self.model)

        with transaction.atomic():
            self.model.objects.bulk_create(instances, batch_size=self.batch_size)

        return len(instances)
