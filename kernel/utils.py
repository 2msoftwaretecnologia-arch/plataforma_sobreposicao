import pyproj
from shapely import wkt
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from typing import Any, Dict, List, Optional

from kernel.service.geometry_overlap_service import GeometryOverlapService
from kernel.service.city_state_locator_service import CityStateLocatorService
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

def locate_city_state(wkt_str: str, method: str = 'representative') -> tuple[Optional[str], Optional[str]]:
    """Função auxiliar para localizar cidade e estado a partir de WKT usando CityStateLocatorService."""
    locator = CityStateLocatorService()
    return locator.locate(wkt_str, method)

def extract_geometry(gdf: gpd.GeoDataFrame = None) -> str:
    """
    Lê um shapefile e retorna o primeiro polígono no formato POLYGON ((...))
    """
    # Para cada geometria no arquivo
    for geom in gdf.geometry:
        if geom is None:
            continue
            
        if geom.geom_type == 'Polygon':
            # Extrai as coordenadas do exterior do polígono
            coords = list(geom.exterior.coords)
            # Formata no estilo POLYGON ((x1 y1, x2 y2, ...))
            coord_str = ", ".join([f"{x} {y}" for x, y in coords])
            return f"POLYGON (({coord_str}))"
            
        elif geom.geom_type == 'MultiPolygon':
            # Para multipolígonos, retorna o primeiro polígono
            if len(geom.geoms) > 0:
                primeira_parte = geom.geoms[0]
                coords = list(primeira_parte.exterior.coords)
                coord_str = ", ".join([f"{x} {y}" for x, y in coords])
                return f"POLYGON (({coord_str}))"
    
    print("Erro: Nenhuma geometria válida encontrada no arquivo")
    return None


def should_include_by_percentage(
    overlap_area: float,
    total_area: float,
    limit_percentage: float
) -> bool:
    """
    Define se um item deve ser incluído com base no percentual de sobreposição.

    - Retorna True quando o percentual de sobreposição é menor que o limite.
    - Caso total_area seja None ou menor/igual a 0, não aplica a regra e retorna True.
    - Em caso de erro de cálculo, retorna True por segurança.
    """
    try:
        if total_area is None or total_area <= 0:
            return True

        overlap_percentage = overlap_area / total_area
        return overlap_percentage < limit_percentage

    except Exception:
        return True
