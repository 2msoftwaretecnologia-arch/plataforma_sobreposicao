from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection
import numpy as np

from deforestation_fires.models import DeforestationMapbiomas
from kernel.service.geometry_processing_service import GeometryProcessingService


class Command(BaseCommand):
    help = "Processa dados geoespaciais de deforestation mapbiomas em paralelo com particionamento e hash única."

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
                obj, created = DeforestationMapbiomas.objects.get_or_create(
                    hash_id=formatted["hash_id"],
                    defaults={
                        "alert_code": formatted["alert_code"],
                        "detection_year": formatted["detection_year"],
                        "source": formatted["source"],
                        "geometry": formatted["geometry"],
                        "created_by": formatted["created_by"],
                    }
                )
                results.append(obj.alert_code)
                
                if created:
                    GeometryProcessingService(DeforestationMapbiomas).process_instance(obj)
                    print(f"[OK] {obj.alert_code}")
                else:
                    print(f"[SKIP] {obj.alert_code} já existe")

            except Exception as e:
                print(f"[ERRO THREAD] {e}")

        # Fecha conexão (boa prática quando usando threads)
        connection.close()

        return results

    # =============================
    # Execução principal
    # =============================
    def handle(self, *args, **options):
        print("Iniciando processamento de Deforestation Mapbiomas em threads...")

        num_threads = options["threads"]
        user = self.get_user()

        archive_path = get_file_management()
        
        if not archive_path:
            raise CommandError("Nenhum arquivo de Deforestation Mapbiomas foi configurado.")
        
        if not archive_path.deforestation_mapbiomas_zip_file.path:
            raise CommandError("Nenhum arquivo de Deforestation Mapbiomas foi configurado.")
        
        df = gpd.read_file(archive_path.deforestation_mapbiomas_zip_file.path)

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
    # Funções utilitárias
    # =============================
    @staticmethod
    def format_data(row, user):
        return {
            "alert_code": str(row.get("CODEALERTA")),
            "detection_year": str(row.get("ANODETEC")),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Deforestation Mapbiomas"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
