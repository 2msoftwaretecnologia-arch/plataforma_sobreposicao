from django.contrib.gis.geos import GEOSGeometry


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
            - geometry (TextField com WKT)
            - usable_geometry (GeometryField SRID=4674)
            - area_m2 (FloatField)
            - area_ha (FloatField)
        """
        self.model = model

    # ============================================================
    # 1) CONVERT WKT → GEOSGeometry
    # ============================================================
    def convert_wkt_to_geometry(self):
        """
        Reads WKT from geometry field and converts it into a
        GEOSGeometry MultiPolygon with SRID=4674.
        """
        queryset = self.model.objects.filter(
            geometry__isnull=False,
            usable_geometry__isnull=True
        )

        count = 0
        for obj in queryset:
            try:
                geom = GEOSGeometry(obj.geometry, srid=4674)

                if not geom.valid:
                    geom = geom.buffer(0)

                obj.usable_geometry = geom
                obj.save(update_fields=["usable_geometry"])    
                count += 1

            except Exception:
                continue

        return count

    # ============================================================
    # 2) FIX WRONG SRID
    # ============================================================
    def fix_srid(self):
        """
        Ensures usable_geometry always has SRID 4674.
        """
        queryset = self.model.objects.exclude(
            usable_geometry__isnull=True
        ).exclude(
            usable_geometry__srid=4674
        )

        count = 0
        for obj in queryset:
            try:
                obj.usable_geometry.srid = 4674
                obj.save(update_fields=["usable_geometry"])
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
        queryset = self.model.objects.exclude(usable_geometry__isnull=True)

        count = 0
        for obj in queryset:
            try:
                geom_utm = obj.usable_geometry.transform(31982, clone=True)

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

    # ============================================================
    # 5) PROCESSAR OBJETO ÚNICO
    # ============================================================
    def process_instance(self, obj):
        """
        Processa um único objeto:
        - Converte WKT (field `geometry`) para GEOSGeometry com SRID 4674
        - Corrige SRID se necessário
        - Calcula área fixa (m² e ha) em UTM 22S (EPSG:31982)
        """
        try:
            if not getattr(obj, "geometry", None):
                return False

            geom = GEOSGeometry(obj.geometry, srid=4674)
            if not geom.valid:
                geom = geom.buffer(0)

            geom.srid = 4674

            geom_utm = geom.transform(31982, clone=True)
            area_m2 = geom_utm.area
            area_ha = area_m2 / 10000

            obj.usable_geometry = geom
            obj.area_m2 = area_m2
            obj.area_ha = area_ha
            obj.save(update_fields=["usable_geometry", "area_m2", "area_ha"])
            return True
        except Exception:
            return False
