from control_panel.utils import get_file_management
import geopandas as gpd
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import connection
import numpy as np

from deforestation_fires.models import Embargoes
from kernel.service.geometry_processing_service import GeometryProcessingService


class Command(BaseCommand):
    help = "Processa dados geoespaciais de embargoe em paralelo com particionamento e hash única."

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
                obj, created = Embargoes.objects.get_or_create(
                    hash_id=formatted["hash_id"],
                    defaults={
                        "property_name": formatted["property_name"],
                        "type_area": formatted["type_area"],
                        "number_infraction_act": formatted["number_infraction_act"],
                        "nome_embargado": formatted["nome_embargado"],
                        "cpf_cnpj_embargado": formatted["cpf_cnpj_embargado"],
                        "control_unity": formatted["control_unity"],
                        "process_number": formatted["process_number"],
                        "act_description": formatted["act_description"],
                        "infraction_description": formatted["infraction_description"],
                        "embargoe_date": formatted["embargoe_date"],
                        "priting_date": formatted["priting_date"],
                        "source": formatted["source"],
                        "geometry": formatted["geometry"],
                        "created_by": formatted["created_by"],
                    }
                )
                results.append(obj.property_name)
                
                if created:
                    GeometryProcessingService(Embargoes).process_instance(obj)
                    print(f"[OK] {obj.property_name}")
                else:
                    print(f"[SKIP] {obj.property_name} já existe")

            except Exception as e:
                print(f"[ERRO THREAD] {e}")

        # Fecha conexão (boa prática quando usando threads)
        connection.close()

        return results

    # =============================
    # Execução principal
    # =============================
    def handle(self, *args, **options):
        print("Iniciando processamento de Embargoe em threads...")

        num_threads = options["threads"]
        user = self.get_user()

        archive_path = get_file_management()
        
        if not archive_path:
            raise CommandError("Nenhum arquivo de Embargoe foi configurado.")
        
        if not archive_path.adm_embargos_ibama_a_zip_file.path:
            raise CommandError("Nenhum arquivo de Embargoe foi configurado.")
        
        df = gpd.read_file(archive_path.adm_embargos_ibama_a_zip_file.path)

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
            "property_name": str(row.get("nome_imove")),
            "type_area": str(row.get("tipo_area")),
            "number_infraction_act": str(row.get("num_auto_i")),
            "nome_embargado": str(row.get("nome_embar")),
            "cpf_cnpj_embargado": str(row.get("cpf_cnpj_e")),
            "control_unity": str(row.get("unidade_c")),
            "process_number": str(row.get("num_proce")),
            "act_description": str(row.get("des_tad")),
            "infraction_description": str(row.get("des_infrac")),
            "embargoe_date": str(row.get("data_embarg")),
            "priting_date": str(row.get("data_impres")),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Embargoe"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
