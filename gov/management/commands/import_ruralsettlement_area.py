from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection
import numpy as np

from gov.models import Ruralsettlement
from kernel.service.geometry_processing_service import GeometryProcessingService


class Command(BaseCommand):
    help = "Processa dados geográficos de assentamentos rurais em paralelo com particionamento e hash única."

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
                obj, created = Ruralsettlement.objects.get_or_create(
                    hash_id=formatted["hash_id"],
                    defaults={
                        "project_name": formatted["project_name"],
                        "method_obtaining": formatted["method_obtaining"],
                        "geometry": formatted["geometry"],
                        "created_by": formatted["created_by"],
                        "source": formatted["source"],
                    }
                )
                results.append(obj.project_name)
                
                if created:
                    GeometryProcessingService(Ruralsettlement).process_instance(obj)
                    print(f"[OK] {obj.project_name}")
                else:
                    print(f"[SKIP] {obj.project_name} já existe")

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
            raise CommandError("Nenhum arquivo de assentamento rural foi configurado.")
        
        if not archive_path.ruralsettlement_zip_file.path:
            raise CommandError("Nenhum arquivo de assentamento rural foi configurado.")
        
        df = gpd.read_file(archive_path.ruralsettlement_zip_file.path)

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
            "project_name": row.get("nome_proje"),
            "method_obtaining": row.get("forma_obte"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Assentamento Rural"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
