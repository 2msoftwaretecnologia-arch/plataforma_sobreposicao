from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection
import numpy as np

from naturatins.models import Quilombolas


class Command(BaseCommand):
    help = "Processa dados geoespaciais de quilombolas em paralelo com particionamento e hash única."

    def add_arguments(self, parser):
        parser.add_argument(
            "--threads",
            type=int,
            default=4,
            help="Número de threads para processamento paralelo."
        )

    def get_user(self):
        user = User.objects.first()
        if not user:
            raise CommandError("Nenhum usuário encontrado.")
        return user

    # =============================
    # Função executada pela thread
    # =============================
    def process_partition(self, partition_df, user):
        """Processa uma partição do DataFrame em uma thread separada."""
        results = []

        for _, row in partition_df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)

            try:
                obj, created = Quilombolas.objects.get_or_create(
                    defaults=formatted
                )
                results.append(obj.name)
                
                if created:
                    print(f"[OK] {obj.name}")
                else:
                    print(f"[SKIP] {obj.name} já existe")

            except Exception as e:
                print(f"[ERRO THREAD] {e}")

        # Fecha conexão (boa prática quando usando threads)
        connection.close()

        return results

    # =============================
    # Execução principal
    # =============================
    def handle(self, *args, **options):
        print("Iniciando processamento em threads...")

        num_threads = options["threads"]
        user = self.get_user()

        archive_path = get_file_management()
        
        if not archive_path:
            raise CommandError("Nenhum arquivo de quilombolas foi configurado.")
        
        if not archive_path.quilombolas_zip_file.path:
            raise CommandError("Nenhum arquivo de quilombolas foi configurado.")
        
        df = gpd.read_file(archive_path.quilombolas_zip_file.path)
        
        print(f"Total de linhas: {len(df)}")

        # Dividir o DataFrame em N partes
        partitions = np.array_split(df, num_threads)

        all_results = []

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(self.process_partition, part, user)
                for part in partitions
            ]

            for future in as_completed(futures):
                all_results.extend(future.result())

        print("Registros inseridos:")
        for r in all_results:
            print(" →", r)

        print("Processamento paralelo concluído com sucesso!")

    # =============================
    # Funções utilitárias GIS
    # =============================
        # =============================
    # Funções utilitárias
    # =============================
    @staticmethod
    def fix_srid(geom: GEOSGeometry, expected_srid=4674) -> GEOSGeometry:
        """Garante que a geometria tem o SRID correto."""
        if geom is None:
            return None
        if geom.srid != expected_srid:
            geom = geom.clone()
            geom.srid = expected_srid
        return geom

    @staticmethod
    def transform_to_utm(geom: GEOSGeometry, utm_srid=31982) -> GEOSGeometry:
        """Transforma a geometria para UTM (métrico)."""
        if geom is None:
            return None
        return geom.transform(utm_srid, clone=True)

    @staticmethod
    def calc_area_m2(geom_utm: GEOSGeometry) -> float:
        if geom_utm is None:
            return 0.0
        return geom_utm.area

    @staticmethod
    def calc_area_ha(area_m2: float) -> float:
        return area_m2 / 10000

    def format_data(self, row, user):
        """Formata os dados de uma linha do DataFrame."""

        # Carregar a geometria corretamente
        raw_geom = row.get("geometry_new")
        geom = GEOSGeometry(str(raw_geom)) if raw_geom else None

        # Corrigir SRID
        geom_fixed = self.fix_srid(geom)

        # Transformar em métrico
        geom_utm = self.transform_to_utm(geom_fixed)

        # Calcular área
        area_m2 = self.calc_area_m2(geom_utm)
        area_ha = self.calc_area_ha(area_m2)

        return {
            "name": row.get("nm_comunid"),
            "geometry": GEOSGeometry(str(row.get("geometry"))),
            "geometry_new": geom_fixed,      # geometria corrigida (EPSG 4674)
            "area_m2": area_m2,
            "area_ha": area_ha,
            "created_by": user,
            "source": "Base Quilombolas",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        """
        Agora inclui área + geometria normalizada → garante unicidade real.
        """
        compact = {
            "name": data["name"],
            "geometry_new": data["geometry_new"].wkt if data["geometry_new"] else None,
            "area_m2": data["area_m2"],
        }
        json_str = json.dumps(compact, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
