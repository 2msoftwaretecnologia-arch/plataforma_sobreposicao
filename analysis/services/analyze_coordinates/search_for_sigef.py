from django.contrib.gis.geos import GEOSGeometry

from gov.models import Sigef
from .search_all import SearchAll


class SearchForSigef:
    """Cruza uma parcela do SIGEF (pelo código da parcela) com todas as bases —
    o equivalente ao `SearchForCar` para o SIGEF. A própria parcela não
    aparece na camada do SIGEF (ver `OverlapService._is_target_itself`)."""

    def execute(self, parcel_code: str, save_debug_files: bool = True) -> dict:
        obj = Sigef.objects.filter(installment_code__iexact=(parcel_code or '').strip()).first()
        if obj is None:
            return {}
        if obj.usable_geometry is None:
            try:
                geom = GEOSGeometry(obj.geometry, srid=4674)
                obj.usable_geometry = geom if geom.valid else geom.buffer(0)
            except Exception:
                return {}
        return SearchAll().execute(obj, save_debug_files=save_debug_files)
