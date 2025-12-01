import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from environmental_layers.models import IndigenousArea
from kernel.service.geometry_processing_service import GeometryProcessingService


class IndigenousAreaImporter:
    def __init__(self, user=None):
        self.user = user

    def _get_user(self):
        if self.user:
            return self.user
        user = User.objects.first()
        if not user:
            raise ValueError("Nenhum usuário encontrado.")
        return user

    @staticmethod
    def format_data(row, user):
        return {
            "indigenous_name": row.get("NOME_AREA"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Indígena",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.indigenous_zip_file.path:
            raise ValueError("Nenhum arquivo de indígena foi configurado.")
        df = gpd.read_file(archive_path.indigenous_zip_file.path, encoding="utf-8")
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = IndigenousArea.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "indigenous_name": formatted["indigenous_name"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                }
            )
            print(f"[OK] {obj.indigenous_name}" if created else f"[SKIP] {obj.indigenous_name} já existe")
        GeometryProcessingService(IndigenousArea).process_all()

