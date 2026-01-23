import geopandas as gpd
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from gov.models import Sigef
from kernel.service.geometry_processing_service import GeometryProcessingService
from kernel.utils import reset_db



class SigefImporter:
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
            "name": row.get("nome_area") if row.get("nome_area") else "Sem Nome",
            "installment_code": row.get("parcela_co") if row.get("parcela_co") else "Sem Parcela",
            "property_code": row.get("propriedade_co") if row.get("propriedade_co") else "Sem Propriedade" ,
            "status": row.get("status") if row.get("status") else "Sem Status",
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Sigef",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Sigef)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.sigef_zip_file.path:
            raise ValueError("Nenhum arquivo de sigef foi configurado.")
        df = gpd.read_file(archive_path.sigef_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Sigef.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "name": formatted["name"],
                    "installment_code": formatted["installment_code"],
                    "property_code": formatted["property_code"],
                    "status": formatted["status"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                    "source": formatted["source"],
                },
            )
            if created:
                GeometryProcessingService(Sigef).process_instance(obj)
                print(f"[OK] {obj.name}")
            else:
                print(f"[SKIP] {obj.name} já existe")
