import math
from functools import lru_cache

from shapely.geometry import MultiPolygon, Polygon
from shapely.prepared import prep
from shapely.wkt import loads

class GeometryParser:
    def parse(self, wkt):
        try:
            if not wkt or wkt.strip() == "":
                return None
            geometry = loads(wkt)
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
                if not geometry.is_valid:
                    return None
            return geometry
        except Exception:
            return None

class BoundsChecker:
    @staticmethod
    def intersects(geom1, geom2):
        bounds1 = geom1.bounds
        bounds2 = geom2.bounds
        return not (bounds1[2] < bounds2[0] or bounds2[2] < bounds1[0] or 
                    bounds1[3] < bounds2[1] or bounds2[3] < bounds1[1])

class AreaConverter:
    def __init__(self, degree_to_meters_lat=111320):
        self.DEGREE_TO_METERS_LAT = degree_to_meters_lat

    def to_hectares(self, geometry):
        try:
            centroid = geometry.centroid
            mean_latitude = centroid.y
            cos_lat = math.cos(math.radians(mean_latitude))
            degree_to_meters_lon = self.DEGREE_TO_METERS_LAT * cos_lat
            area_degrees = geometry.area
            area_meters = area_degrees * self.DEGREE_TO_METERS_LAT * degree_to_meters_lon
            hectares_area = abs(area_meters) / 10000
            return hectares_area
        except Exception:
            area_meters = geometry.area * self.DEGREE_TO_METERS_LAT * self.DEGREE_TO_METERS_LAT
            return area_meters / 10000

class OverlapChecker:
    def __init__(self, min_overlap_area=0.0001, degree_to_meters_lat=111320):
        self.MIN_OVERLAP_AREA = min_overlap_area
        self.parser = GeometryParser()
        self.bounds = BoundsChecker()
        self.converter = AreaConverter(degree_to_meters_lat)

    @lru_cache(maxsize=2048)
    def _get_geometria_cached(self, wkt):
        return self.parser.parse(wkt)

    @lru_cache(maxsize=128)
    def _get_prepared_geometry(self, wkt):
        geometry = self._get_geometria_cached(wkt)
        return prep(geometry) if geometry is not None else None

    def _convert_to_hectares_optimized(self, geometry):
        return self.converter.to_hectares(geometry) if geometry is not None else 0

    def check_overlap(self, wkt1, wkt2, name1="Polígono 1", name2="Polígono 2"):
        try:
            poly1 = self._get_geometria_cached(wkt1)
            poly2 = self._get_geometria_cached(wkt2)
            if poly1 is None or poly2 is None:
                return None
            if not BoundsChecker.intersects(poly1, poly2):
                return 0
            prepared_poly1 = self._get_prepared_geometry(wkt1)
            if prepared_poly1 is not None:
                if not prepared_poly1.intersects(poly2):
                    return 0
            elif not poly1.intersects(poly2):
                return 0
            intersection = poly1.intersection(poly2)
            if intersection.is_empty:
                return 0
            hectares_area = self._convert_to_hectares_optimized(intersection)
            if hectares_area < self.MIN_OVERLAP_AREA:
                return 0
            return hectares_area
        except Exception:
            return None