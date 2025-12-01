from kernel.service.geometry_processing_service import GeometryProcessingService
import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from environmental_layers.models import ZoningArea


class ZoningAreaImporter:
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
            "zone_name": row.get("nm_zona"),
            "zone_acronym": row.get("zona_sigla"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Zoneamento",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.zoning_zip_file.path:
            raise ValueError("Nenhum arquivo de zoneamento foi configurado.")
        df = gpd.read_file(archive_path.zoning_zip_file.path, encoding="utf-8")
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = ZoningArea.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "zone_name": formatted["zone_name"],
                    "zone_acronym": formatted["zone_acronym"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                },
            )
            if created:
                GeometryProcessingService(ZoningArea).process_instance(obj)
                print(f"[OK] {obj.zone_name}")
            else:
                print(f"[SKIP] {obj.zone_name} já existe")
