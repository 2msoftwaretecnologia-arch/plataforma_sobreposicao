import geopandas as gpd
import hashlib
import json
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.auth.models import User
from control_panel.utils import get_file_management
from naturatins.models import Quilombolas
from kernel.service.geometry_processing_service import GeometryProcessingService

from kernel.utils import reset_db

class QuilombolasImporter:
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
    def fix_srid(geom: GEOSGeometry, expected_srid=4674) -> GEOSGeometry:
        if geom is None:
            return None
        if geom.srid != expected_srid:
            geom = geom.clone()
            geom.srid = expected_srid
        return geom

    @staticmethod
    def transform_to_utm(geom: GEOSGeometry, utm_srid=31982) -> GEOSGeometry:
        if geom is None:
            return None
        return geom.transform(utm_srid, clone=True)

    @staticmethod
    def calc_area_m2(geom_utm: GEOSGeometry) -> float:
        if geom_utm is None:
            return 0.0
        return geom_utm.area

    @staticmethod
    def calc_area_ha(area_m2: float) -> float:
        return area_m2 / 10000

    def format_data(self, row, user):
        raw_geom = row.get("usable_geometry")
        geom = GEOSGeometry(str(raw_geom)) if raw_geom else None
        geom_fixed = self.fix_srid(geom)
        geom_utm = self.transform_to_utm(geom_fixed)
        area_m2 = self.calc_area_m2(geom_utm)
        area_ha = self.calc_area_ha(area_m2)
        return {
            "name": row.get("nm_comunid"),
            "geometry": str(row.get("geometry")),
            "usable_geometry": geom_fixed,
            "area_m2": area_m2,
            "area_ha": area_ha,
            "created_by": user,
            "source": "Base Quilombolas",
        }

    @staticmethod
    def generate_hash(data: dict) -> str:
        compact = {
            "name": data["name"],
            "usable_geometry": data["usable_geometry"].wkt if data["usable_geometry"] else None,
            "area_m2": data["area_m2"],
        }
        json_str = json.dumps(compact, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def execute(self):
        reset_db(Quilombolas)
        user = self._get_user()
        archive_path = get_file_management()
        if not archive_path or not archive_path.quilombolas_zip_file.path:
            raise ValueError("Nenhum arquivo de quilombolas foi configurado.")
        df = gpd.read_file(archive_path.quilombolas_zip_file.path, encoding="utf-8")
        for _, row in df.iterrows():
            formatted = self.format_data(row, user)
            formatted["hash_id"] = self.generate_hash(formatted)
            obj, created = Quilombolas.objects.get_or_create(
                hash_id=formatted["hash_id"],
                defaults=formatted
            )
            if created:
                GeometryProcessingService(Quilombolas).process_instance(obj)
                print(f"[OK] {obj.name}")
            else:
                print(f"[SKIP] {obj.name} já existe")
