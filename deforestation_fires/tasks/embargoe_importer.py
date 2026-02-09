import geopandas as gpd
from decimal import Decimal, InvalidOperation
import hashlib
import json
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from deforestation_fires.models import Embargoes
from kernel.service.geometry_processing_service import GeometryProcessingService
from kernel.service.database_maintenance_service import DatabaseMaintenanceService
from kernel.utils import reset_db


class EmbargoesImporter:
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
            "property_name": str(row.get("nome_imove")),
            "type_area": str(row.get("tipo_area")),
            "number_infraction_act": str(row.get("num_auto_i")),
            "nome_embargado": str(row.get("nome_embar")),
            "cpf_cnpj_embargado": str(row.get("cpf_cnpj_e")),
            "control_unity": str(row.get("unid_contr")),
            "process_number": str(row.get("num_proces")),
            "act_description": str(row.get("des_tad")),
            "infraction_description": str(row.get("des_infrac")),
            "embargoe_date": str(row.get("dat_embarg")),
            "priting_date": str(row.get("dat_impres")),
            "geometry": str(row.get("geometry")),
            "created_by": user,
            "source": "Base Deforestation Mapbiomas"    
        }


    @staticmethod
    def generate_hash(data: dict) -> str:
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Embargoes)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.adm_embargos_ibama_a_zip_file:
            raise ValueError("Nenhum arquivo de Embargoes foi configurado.")
        df = gpd.read_file(archive_path.adm_embargos_ibama_a_zip_file.path)
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Embargoes.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults={
                    "property_name": formatted["property_name"],
                    "type_area": formatted["type_area"],
                    "number_infraction_act": formatted["number_infraction_act"],
                    "nome_embargado": formatted["nome_embargado"],
                    "cpf_cnpj_embargado": formatted["cpf_cnpj_embargado"],
                    "control_unity": formatted["control_unity"],
                    "process_number": formatted["process_number"],
                    "act_description": formatted["act_description"],
                    "infraction_description": formatted["infraction_description"],
                    "embargoe_date": formatted["embargoe_date"],
                    "priting_date": formatted["priting_date"],
                    "source": formatted["source"],
                    "geometry": formatted["geometry"],
                    "created_by": formatted["created_by"],
                },
            )

            if created:
                GeometryProcessingService(Embargoes).process_instance(obj)
                print(f"[OK] {obj.property_name}")
            else:
                print(f"[SKIP] {obj.property_name} já existe")
