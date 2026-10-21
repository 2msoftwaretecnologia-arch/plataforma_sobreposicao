import time

import pyogrio
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from control_panel.layer_registry import LAYER_REGISTRY
from kernel.service.bulk_shapefile_importer import SRID
from kernel.utils import model_count_cache_key, reset_db


class Command(BaseCommand):
    help = (
        "Importa um arquivo grande do SICAR (ZIP ou GeoPackage) para uma camada do "
        "LAYER_REGISTRY lendo em blocos, para não carregar o arquivo inteiro na "
        "memória. Ex.: manage.py import_declared_theme DeclaredApp /app/media/sicar/APPS.zip"
    )

    def add_arguments(self, parser):
        parser.add_argument("modelo", help="Chave do LAYER_REGISTRY (ex.: DeclaredApp).")
        parser.add_argument("arquivo", help="Caminho do .zip/.gpkg baixado do SICAR.")
        parser.add_argument("--chunk-size", type=int, default=5000)
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Não zera a tabela: continua a partir da quantidade de registros já gravados.",
        )

    def handle(self, modelo, arquivo, chunk_size, resume, **options):
        entry = LAYER_REGISTRY.get(modelo)
        if not entry:
            raise CommandError(f"Camada desconhecida: {modelo}")
        model, importer = entry["model"], entry["importer"]()
        user = importer._get_user()

        # O SICAR divide temas grandes em vários shapefiles no mesmo ZIP
        # (APPS_1, APPS_2...) e o GeoPackage traz a tabela DICIONARIO, sem geometria.
        layers = [name for name, geometry_type in pyogrio.list_layers(arquivo) if geometry_type]
        counts = {name: pyogrio.read_info(arquivo, layer=name)["features"] for name in layers}
        total_features = sum(counts.values())
        self.stdout.write(f"{modelo}: {total_features} feições em {arquivo} {counts}")

        # Cada bloco é confirmado separadamente, então a quantidade de registros
        # na tabela é sempre a quantidade de feições já processadas, na ordem do arquivo.
        done = model.objects.count() if resume else 0
        if not resume:
            with transaction.atomic():
                reset_db(model)

        blocks, offset = [], 0
        for name in layers:
            start = max(0, done - offset)
            blocks += [(name, skip) for skip in range(start, counts[name], chunk_size)]
            offset += counts[name]

        started, done_before = time.time(), done
        for layer, skip in blocks:
            df = pyogrio.read_dataframe(
                arquivo, layer=layer, skip_features=skip, max_features=chunk_size, encoding="utf-8"
            )
            if df.crs is not None and df.crs.to_epsg() != SRID:
                df = df.to_crs(epsg=SRID)
            instances = [importer._build_instance(row, user) for _, row in df.iterrows()]
            del df

            connection.close_if_unusable_or_obsolete()
            with transaction.atomic():
                model.objects.bulk_create(instances, batch_size=importer.batch_size)
            done += len(instances)

            elapsed = time.time() - started
            remaining = elapsed / (done - done_before) * (total_features - done)
            self.stdout.write(
                f"  {done}/{total_features} ({done / total_features:.0%}) "
                f"em {elapsed / 60:.1f} min, faltam ~{remaining / 60:.0f} min"
            )

        cache.delete(model_count_cache_key(model))
        self.stdout.write(self.style.SUCCESS(f"{modelo}: {model.objects.count()} registros no banco."))
