import pyproj
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon
from typing import Any, Dict, List, Optional

from kernel.service.geometry_overlap_service import GeometryOverlapService
from logica_sobreposicao import VerificadorSobreposicao


def calculate_safe_overlap(
    checker: VerificadorSobreposicao,
    polygon_wkt: str,
    multipolygon_wkt: str,
) -> Optional[float]:
    try:
        return checker.verificar_sobreposicao(
            polygon_wkt,
            multipolygon_wkt,
        )
    except Exception:
        return None


def base_result(
    base_name: str,
    found_areas: List[Dict[str, Any]],
    quantity_not_evaluated: int,
) -> Dict[str, Any]:
    return {
        "nome_base": base_name,
        "areas_encontradas": found_areas,
        "quantidade_nao_avaliados": quantity_not_evaluated,
        "total_areas_com_sobreposicao": len(found_areas),
    }
    

def calculate_area_ha(wkt_str: str) -> float:
    """
    Calcula a área (em hectares) de um POLYGON ou MULTIPOLYGON WKT (em WGS84 lon/lat)
    """
    GEOD = pyproj.Geod(ellps="WGS84")
    geom = wkt.loads(wkt_str)

    def area_m2(poly: Polygon) -> float:
        # Calcula área geodésica real (considerando a curvatura da Terra)
        try:
            area, _ = GEOD.geometry_area_perimeter(poly)
            return abs(area)
        except Exception:
            x, y = poly.exterior.xy
            area_ext, _ = GEOD.polygon_area_perimeter(x, y)
            area_total = abs(area_ext)
            for ring in poly.interiors:
                xh, yh = ring.xy
                area_hole, _ = GEOD.polygon_area_perimeter(xh, yh)
                area_total -= abs(area_hole)
            return area_total

    if isinstance(geom, Polygon):
        area_m2_total = area_m2(geom)
    elif isinstance(geom, MultiPolygon):
        area_m2_total = sum(area_m2(g) for g in geom.geoms)
    else:
        raise ValueError("A geometria deve ser POLYGON ou MULTIPOLYGON.")

    return area_m2_total / 10_000  # converte m² para hectares

