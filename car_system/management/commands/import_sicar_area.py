from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection

from car_system.models import SicarRecord
from kernel.service.geometry_processing_service import GeometryProcessingService


class Command(BaseCommand):
    help = "Insere registros SICAR com processamento paralelo e hash única por linha."

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

    # =============================================================
    # Função executada em cada thread (processa 1 partição do DF)
    # =============================================================
    def process_partition(self, partition_df, user):
        results = []

        for _, row in partition_df.iterrows():
            formatted = self.format_data(row, user)

            try:
                obj, created = SicarRecord.objects.get_or_create(
                    car_number=formatted["car_number"],
                    defaults={
                        "status": formatted["status"],
                        "geometry": formatted["geometry"],
                        "last_update": formatted["last_update"],
                        "created_by": formatted["created_by"],
                        "source": formatted["source"]
                    }
                )

                if created:
                    GeometryProcessingService(SicarRecord).process_instance(obj)
                    print(f"[CRIADO] CAR: {obj.car_number}")
                else:
                    print(f"[JÁ EXISTIA] CAR: {obj.car_number}")
   
                results.append(obj.car_number)

            except Exception as e:
                print(f"[ERRO THREAD] {e}")

        # Fecha conexão após uso
        connection.close()
        return results

    # =============================================================
    # Execução principal
    # =============================================================
    def handle(self, *args, **options):
        print("Iniciando leitura e processamento paralelo...")

        num_threads = options["threads"]
        user = self.get_user()

        archive_path = get_file_management()
        
        if not archive_path:
            raise CommandError("Nenhum arquivo de SICAR foi configurado.")
        
        if not archive_path.sicar_zip_file.path:
            raise CommandError("Nenhum arquivo de SICAR foi configurado.")
        
        df = gpd.read_file(archive_path.sicar_zip_file.path, encoding="utf-8")
        df = df[["cod_imovel", "ind_status", "dat_atuali", "geometry"]]
        df = self.filter_existing_hashes(df)
    
        print(f"Total de linhas encontradas: {len(df)}")

        # Particionar o DataFrame
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

        print("Processamento concluído com sucesso.")

    # =============================================================
    # Funções auxiliares
    # =============================================================
    def format_data(self, row, user):
        return {
            "car_number": row.get("cod_imovel"),
            "status": row.get("ind_status"),
            "geometry": str(row.get("geometry")),
            "last_update": self.format_date(row.get("dat_atuali")),
            "created_by": user,
            "source": "Base Sicar"
        }

    def format_date(self, date_str):
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except (ValueError, TypeError):
            return None
        
    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    @staticmethod
    def filter_existing_hashes(df):
        existing_hashes = set(
            SicarRecord.objects.values_list("car_number", flat=True)
        )
        return df[~df["cod_imovel"].isin(existing_hashes)]
    
    @staticmethod
    def tractive_df(df, column_name: str):
        return df[column_name].dropna()
