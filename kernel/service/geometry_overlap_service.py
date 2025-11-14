from __future__ import annotations
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely.wkt import loads
import math
from typing import Optional, Union


# ===============================
# Serviço: conversão WKT → geometria
# ===============================
class GeometryParser:
    
    @staticmethod
    def parse(wkt: str) -> Optional[BaseGeometry]:
        """Converte WKT em geometria Shapely. Retorna None se inválido."""
        if not wkt or not wkt.strip():
            return None

        try:
            geom = loads(wkt)

            if not geom.is_valid:
                geom = geom.buffer(0)
                if not geom.is_valid:
                    return None

            return geom

        except Exception:
            return None


# ========================================
# Serviço: operações geométricas auxiliares
# ========================================
class GeometryUtils:
    @staticmethod
    def bounds_intersect(g1: BaseGeometry, g2: BaseGeometry) -> bool:
        """Verifica se os bounding boxes das geometrias se intersectam."""
        b1 = g1.bounds  # (minx, miny, maxx, maxy)
        b2 = g2.bounds

        return not (
            b1[2] < b2[0] or
            b2[2] < b1[0] or
            b1[3] < b2[1] or
            b2[3] < b1[1]
        )


# ============================================
# Serviço: cálculos de área e conversões
# ============================================
class AreaCalculator:

    @staticmethod
    def to_hectares(geom: BaseGeometry) -> float:
        GRAU_PARA_METROS_LAT = 111320

        """Converte área de graus² para hectares usando latitude média."""
        try:
            lat = geom.centroid.y
            cos_lat = math.cos(math.radians(lat))

            grau_para_metros_lon = GRAU_PARA_METROS_LAT * cos_lat

            area_graus = geom.area
            area_m2 = area_graus * GRAU_PARA_METROS_LAT * grau_para_metros_lon

            return abs(area_m2) / 10000  # m² → hectares

        except Exception:
            fallback = geom.area * GRAU_PARA_METROS_LAT * GRAU_PARA_METROS_LAT
            return fallback / 10000


# ====================================================
# Serviço principal: analisa sobreposição entre formas
# ====================================================
class GeometryOverlapService:
    AREA_MINIMA_HECTARES = 0.0001

    def __init__(
        self,
        parser: GeometryParser = None,
        utils: GeometryUtils = None,
        area_calc: AreaCalculator = None,
    ):
        self.parser = parser or GeometryParser
        self.utils = utils or GeometryUtils
        self.area_calc = area_calc or AreaCalculator

    def check_overlap(
        self,
        wkt1: str,
        wkt2: str,
    ) -> Optional[float]:
        """
        Entrada:
            wkt1: str – geometria 1 em WKT
            wkt2: str – geometria 2 em WKT

        Saída:
            float – área da sobreposição em hectares
            0.0 – se não houver sobreposição ou área mínima
            None – se alguma geometria for inválida
        """

        g1 = self.parser.parse(wkt1)
        g2 = self.parser.parse(wkt2)

        if g1 is None or g2 is None:
            return None

        # Verificação rápida (bounding box)
        if not self.utils.bounds_intersect(g1, g2):
            return 0.0

        # Verificação de interseção
        if not g1.intersects(g2):
            return 0.0

        inter = g1.intersection(g2)

        if inter.is_empty:
            return 0.0

        # Área em hectares
        area = self.area_calc.to_hectares(inter)

        if area < self.AREA_MINIMA_HECTARES:
            return 0.0

        return area
