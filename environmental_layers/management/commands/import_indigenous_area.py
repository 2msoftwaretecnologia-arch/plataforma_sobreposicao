from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection
import numpy as np

from environmental_layers.models import IndigenousArea
from kernel.service.geometry_processing_service import GeometryProcessingService


class Command(BaseCommand):
    help = "Processa dados geoespaciais em paralelo com particionamento e hash única."

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
                obj, created = IndigenousArea.objects.get_or_create(
                    hash_id=formatted["hash_id"],
                    defaults={
                        "indigenous_name": formatted["indigenous_name"],
                        "geometry": formatted["geometry"],
                        "created_by": formatted["created_by"],
                        "source": formatted["source"],
                    }
                )
                results.append(obj.indigenous_name)
                
                if created:
                    processing = GeometryProcessingService(IndigenousArea)
                    processing.process_instance(obj)
                else:
                    print(f"[SKIP] {obj.indigenous_name} já existe")

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
            raise CommandError("Nenhum arquivo de indígena foi configurado.")
        
        if not archive_path.indigenous_zip_file.path:
            raise CommandError("Nenhum arquivo de indígena foi configurado.")
        
        df = gpd.read_file(archive_path.indigenous_zip_file.path, encoding="utf-8")

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
            "indigenous_name": row.get("NOME_AREA"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Indígena"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
