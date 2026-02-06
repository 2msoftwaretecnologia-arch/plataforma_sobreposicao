import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from seplan.models import Highways
from kernel.service.geometry_processing_service import GeometryProcessingService
from kernel.utils import reset_db



class HighwaysImporter:
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
            "NOME_2011": row.get("NOME_2011") if row.get("NOME_2011") else "Sem Nome",
            "CLAS_2011": row.get("CLAS_2011") if row.get("CLAS_2011") else "Sem Classe",
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Sigef",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Highways)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.highways_zip_file.path:
            raise ValueError("Nenhum arquivo de highways foi configurado.")
        df = gpd.read_file(archive_path.highways_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Highways.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "NOME_2011": formatted["NOME_2011"],
                    "CLAS_2011": formatted["CLAS_2011"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                },
            )
            if created:
                GeometryProcessingService(Highways).process_instance(obj)
                print(f"[OK] {obj.NOME_2011}")
            else:
                print(f"[SKIP] {obj.NOME_2011} já existe")
