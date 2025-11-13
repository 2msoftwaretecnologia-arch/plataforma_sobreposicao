import geopandas as gpd
import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from environmental_layers.models import PhytoecologyArea

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

        archive_path = r'Regiões_Fitoecológicas_IBGE_TO.zip'
        df = gpd.read_file(archive_path, encoding='utf-8')

        print(df.head())
        for _, row in df.iterrows():
            formatted_data = self.format_data(row, user)
            
            formatted_data["hash_id"] = self.generate_hash(formatted_data)
            try:
                zoning_area = PhytoecologyArea.objects.get_or_create(
                    hash_id=formatted_data["hash_id"],
                    phyto_name=formatted_data["phyto_name"],
                    geometry=formatted_data["geometry"],
                    created_by=formatted_data["created_by"],
                    source=formatted_data["source"]
                )
                
                print(f"Inserido: {zoning_area[0].phyto_name}")
            except Exception as e:
                print(f"Erro ao inserir linha: {e}")
                
        print("Processamento concluído com sucesso.")

    @staticmethod
    def format_data(row, user):
        return {
            "phyto_name": row.get("AnáliseCA"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Fitoecologia"
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        """
        Gera uma hash SHA256 determinística a partir dos dados da linha.
        """
        # Ordena o dicionário para garantir consistência
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
