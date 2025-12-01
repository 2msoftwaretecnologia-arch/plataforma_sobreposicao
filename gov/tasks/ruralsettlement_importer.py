import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from gov.models import Ruralsettlement


class RuralsettlementImporter:
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
            "project_name": row.get("nome_proje"),
            "method_obtaining": row.get("forma_obte"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Assentamento Rural",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.ruralsettlement_zip_file.path:
            raise ValueError("Nenhum arquivo de assentamento rural foi configurado.")
        df = gpd.read_file(archive_path.ruralsettlement_zip_file.path, encoding="utf-8")
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Ruralsettlement.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "project_name": formatted["project_name"],
                    "method_obtaining": formatted["method_obtaining"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                },
            )
            print(f"[OK] {obj.project_name}" if created else f"[SKIP] {obj.project_name} já existe")

