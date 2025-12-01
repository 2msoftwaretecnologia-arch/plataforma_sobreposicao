import geopandas as gpd
import hashlib
import json
from datetime import datetime
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from car_system.models import SicarRecord
from kernel.service.geometry_processing_service import GeometryProcessingService


class SicarImporter:
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
    def format_date(date_str):
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def format_data(row, user):
        return {
            "car_number": row.get("cod_imovel"),
            "status": row.get("ind_status"),
            "geometry": str(row.get("geometry")),
            "last_update": SicarImporter.format_date(row.get("dat_atuali")),
            "created_by": user,
            "source": "Base Sicar",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    @staticmethod
    def filter_existing(df):
        existing = set(SicarRecord.objects.values_list("car_number", flat=True))
        return df[~df["cod_imovel"].isin(existing)]

    def execute(self):
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.sicar_zip_file.path:
            raise ValueError("Nenhum arquivo de SICAR foi configurado.")
        df = gpd.read_file(archive_path.sicar_zip_file.path, encoding="utf-8")
        df = df[["cod_imovel", "ind_status", "dat_atuali", "geometry"]]
        df = self.filter_existing(df)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            obj, created = SicarRecord.objects.get_or_create(
                car_number=formatted["car_number"],
                defaults={
                    "status": formatted["status"],
                    "geometry": formatted["geometry"],
                    "last_update": formatted["last_update"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                },
            )
            if created:
                GeometryProcessingService(SicarRecord).process_instance(obj)
                print(f"[CRIADO] CAR: {obj.car_number}")
            else:
                print(f"[JÁ EXISTIA] CAR: {obj.car_number}")
