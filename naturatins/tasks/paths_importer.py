import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from naturatins.models import Paths
from kernel.utils import reset_db



class PathsImporter:
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
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Veredas",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Paths)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.paths_zip_file.path:
            raise ValueError("Nenhum arquivo de veredas foi configurado.")
        df = gpd.read_file(archive_path.paths_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Paths.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                }
            )
            print(f"[OK] {obj.hash_id}" if created else f"[SKIP] {obj.hash_id} já existe")

