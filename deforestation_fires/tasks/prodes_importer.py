import geopandas as gpd
from decimal import Decimal, InvalidOperation
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from deforestation_fires.models import Prodes
from kernel.service.geometry_processing_service import GeometryProcessingService
from kernel.service.database_maintenance_service import DatabaseMaintenanceService
from kernel.utils import reset_db


class ProdesImporter:
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
            "identification": str(row.get("main_class")),
            "image_date": str(row.get("image_date")),
            "year": str(row.get("year")),
            "satelite": str(row.get("satelite")),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Prodes"    
        }


    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Prodes)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.prodes_zip_file:
            raise ValueError("Nenhum arquivo de Prodes foi configurado.")
        df = gpd.read_file(archive_path.prodes_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Prodes.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "identification": formatted["identification"],
                    "image_date": formatted["image_date"],
                    "year": formatted["year"],
                    "satelite": formatted["satelite"],
                    "source": formatted["source"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                },
            )
            
            if created:
                GeometryProcessingService(Prodes).process_instance(obj)
                print(f"[OK] {obj.identification}")
            else:
                print(f"[SKIP] {obj.identification} já existe")
