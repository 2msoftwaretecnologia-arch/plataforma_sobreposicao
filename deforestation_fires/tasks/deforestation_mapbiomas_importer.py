import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from deforestation_fires.models import DeforestationMapbiomas


class DeforestationMapbiomasImporter:
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
            "alert_code": str(row.get("CODEALERTA")),
            "detection_year": str(row.get("ANODETEC")),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Deforestation Mapbiomas"    
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.snic_total_zip_file.path:
            raise ValueError("Nenhum arquivo de Deforestation Mapbiomas foi configurado.")
        df = gpd.read_file(archive_path.deforestation_mapbiomas_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = DeforestationMapbiomas.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "alert_code": formatted["alert_code"],
                    "detection_year": formatted["detection_year"],
                    "source": formatted["source"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                },
            )
            print(f"[OK] {obj.alert_code}" if created else f"[SKIP] {obj.alert_code} já existe")

