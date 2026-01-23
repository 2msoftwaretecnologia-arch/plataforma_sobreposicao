from kernel.service.geometry_processing_service import GeometryProcessingService
import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from environmental_layers.models import EnvironmentalProtectionArea
from kernel.utils import reset_db



class EnvironmentalProtectionAreaImporter:
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
            "unit_name": row.get("Unidades"),
            "domains": row.get("Dominios"),
            "class_group": row.get("Classes"),
            "legal_basis": row.get("FundLegal"),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base APA",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(EnvironmentalProtectionArea)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.environmental_protection_zip_file.path:
            raise ValueError("Nenhum arquivo de APA foi configurado.")
        df = gpd.read_file(archive_path.environmental_protection_zip_file.path, encoding="utf-8")
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = EnvironmentalProtectionArea.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults=formatted,
            )
            if created:
                GeometryProcessingService(EnvironmentalProtectionArea).process_instance(obj)
                print(f"[OK] {obj.unit_name}")
            else:
                print(f"[SKIP] {obj.unit_name} já existe")

