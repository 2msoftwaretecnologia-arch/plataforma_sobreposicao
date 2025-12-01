from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import Transform
from django.db import transaction


class GeometryProcessingService:
    """
    Service responsible for:

    1) Converting WKT → GEOSGeometry (SRID 4674)
    2) Fixing incorrect SRID values
    3) Calculating area in m² and ha using UTM Zone 22S (EPSG:31982)
    """

    def __init__(self, model):
        """
        :param model: Django Model containing:
            - geo_wkt (TextField)
            - geometry_tmp (MultiPolygonField)
            - area_m2 (FloatField)
            - area_ha (FloatField)
        """
        self.model = model

    # ============================================================
    # 1) CONVERT WKT → GEOSGeometry
    # ============================================================
    def convert_wkt_to_geometry(self):
        """
        Reads WKT from geo_wkt field and converts it into a
        GEOSGeometry MultiPolygon with SRID=4674.
        """
        queryset = self.model.objects.filter(
            geometry__isnull=False,
            geometry_new__isnull=True
        )

        count = 0
        for obj in queryset:
            try:
                geom = GEOSGeometry(obj.geo_wkt, srid=4674)

                if not geom.valid:
                    geom = geom.buffer(0)

                obj.geometry_new = geom
                obj.save(update_fields=["geometry_new"])    
                count += 1

            except Exception:
                continue

        return count

    # ============================================================
    # 2) FIX WRONG SRID
    # ============================================================
    def fix_srid(self):
        """
        Ensures geometry_tmp always has SRID 4674.
        """
        queryset = self.model.objects.exclude(
            geometry_new__isnull=True
        ).exclude(
            geometry_new__srid=4674
        )

        count = 0
        for obj in queryset:
            try:
                obj.geometry_new.srid = 4674
                obj.save(update_fields=["geometry_new"])
                count += 1
            except Exception:
                continue

        return count

    # ============================================================
    # 3) CALCULATE AREAS IN UTM ZONE 22S (EPSG:31982)
    # ============================================================
    def calculate_fixed_areas(self):
        """
        Calculates fixed areas in m² and hectares using
        UTM Zone 22S projection (EPSG:31982).
        """
        queryset = self.model.objects.exclude(geometry_new__isnull=True)

        count = 0
        for obj in queryset:
            try:
                geom_utm = obj.geometry_new.transform(31982, clone=True)

                area_m2 = geom_utm.area
                area_ha = area_m2 / 10000

                obj.area_m2 = area_m2
                obj.area_ha = area_ha

                obj.save(update_fields=["area_m2", "area_ha"])
                count += 1

            except Exception:
                continue

        return count

    # ============================================================
    # 4) ORCHESTRATOR
    # ============================================================
    def process_all(self):
        """
        Runs the entire processing pipeline.
        """
        results = {
            "wkt_converted": self.convert_wkt_to_geometry(),
            "srid_fixed": self.fix_srid(),
            "areas_calculated": self.calculate_fixed_areas(),
        }

        return results
