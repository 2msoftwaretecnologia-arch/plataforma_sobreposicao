from django.contrib.gis.geos import GEOSGeometry
from car_system.utils import get_sicar_record
from .search_all import SearchAll


class SearchForCar:
    
    def execute(self, car: str) -> dict:
        car_norm = (car or "").strip()
        qs = get_sicar_record(car_number__iexact=car_norm)
        if not qs.exists():
            return {}
        obj = qs.first()
        geom = getattr(obj, "usable_geometry", None)
        if geom is None:
            try:
                geom = GEOSGeometry(obj.geometry, srid=4674)
                if not geom.valid:
                    geom = geom.buffer(0)
            except Exception:
                return {}
            obj.usable_geometry = geom
        return SearchAll().execute(obj)
