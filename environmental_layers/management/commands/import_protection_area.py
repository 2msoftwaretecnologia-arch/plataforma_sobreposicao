import geopandas as gpd
import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from control_panel.utils import get_file_management
from environmental_layers.models import EnvironmentalProtectionArea
from kernel.service.geometry_processing_service import GeometryProcessingService

class Command(BaseCommand):
    help = "Verifica e insere dados geoespaciais com hash única por linha."

    def get_user(self):
        user = User.objects.first()
        if not user:
            raise CommandError("Nenhum usuário encontrado.")
        return user

    def handle(self, *args, **options):
        print("Iniciando leitura e inserção...")
        user = self.get_user()

        archive_path = get_file_management()
        
        if not archive_path:
            raise CommandError("Nenhum arquivo de APA foi configurado.")
        
        if not archive_path.protection_zip_file.path:
            raise CommandError("Nenhum arquivo de APA foi configurado.")
        
        df = gpd.read_file(archive_path.protection_zip_file.path, encoding="utf-8")

        for _, row in df.iterrows():
            formatted_data = self.format_data(row, user)
            # Aqui você pode salvar no banco (exemplo: MyModel.objects.get_or_create(hash=...))
            formatted_data["hash_id"] = self.generate_hash(formatted_data)
            try:
                protection_area, created = EnvironmentalProtectionArea.objects.get_or_create(
                    hash_id=formatted_data["hash_id"],
                    defaults=formatted_data
                )
                
                if created:
                    GeometryProcessingService(EnvironmentalProtectionArea).process_instance(protection_area)
                    print(f"APA {protection_area.unit_name} criada.")
                else:
                    print(f"APA {protection_area.unit_name} já existe.")
                    
            except Exception as e:
                print(f"Erro ao inserir dados: {e}")
                
        print("Processamento concluído com sucesso.")

    @staticmethod
    def format_data(row, user):
        return {
            "unit_name": row.get("Unidades"),
            "domains": row.get("Dominios"),
            "class_group": row.get("Classes"),
            "legal_basis": row.get("FundLegal"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base APA"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        """
        Gera uma hash SHA256 determinística a partir dos dados da linha.
        """
        # Ordena o dicionário para garantir consistência
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
