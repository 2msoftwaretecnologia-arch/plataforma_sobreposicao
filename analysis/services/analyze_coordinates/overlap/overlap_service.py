from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import Intersection
from django.db.models import F
import pandas as pd

UTM_SRID = 31982  # SIRGAS 2000 / UTM 22S


class OverlapService:
    """
    Service responsible for checking overlaps between a geographic target
    (CAR or external polygon) and environmental layers stored in the database.
    Uses precomputed fields (area_m2, area_ha) for maximum efficiency.
    """

    def __init__(self, target):
        """
        target: Instance of GeometryTarget (universal geometry handler)
        """
        self.target = target
        self.target_geom = target.geometry
        self.target_area_m2 = target.area_m2
        self.target_area_ha = target.area_ha

        if self.target_geom is None:
            raise ValueError("The provided geometry is invalid.")

    # -----------------------------------------------------------
    # Query layers
    # -----------------------------------------------------------
    def get_intersecting(self, layer_model):
        """Return queryset of layer objects that intersect the target geometry."""
        return layer_model.objects.filter(
            geometry_new__intersects=self.target_geom
        )

    # -----------------------------------------------------------
    # Compute intersections
    # -----------------------------------------------------------
    def compute_intersections(self, layer_model):
        """
        Computes intersections between the target geometry and a layer.
        Intersection geometry is transformed to UTM for precise area calculation.
        """
        qs = (
            layer_model.objects
            .filter(geometry_new__intersects=self.target_geom)
            .annotate(intersection=Intersection(F("geometry_new"), self.target_geom))
        )

        results = []

        for obj in qs:
            inter = obj.intersection
            if inter.empty:
                continue

            # Compute intersection area using UTM projection
            inter_utm = inter.transform(UTM_SRID, clone=True)
            inter_area_m2 = inter_utm.area
            inter_area_ha = inter_area_m2 / 10000

            # Percent overlap relative to the target area
            percent_overlap = (
                (inter_area_m2 / self.target_area_m2) * 100
                if self.target_area_m2 > 0 else 0
            )

            results.append({
                "id": obj.id,
                "intersection_area_m2": inter_area_m2,
                "intersection_area_ha": inter_area_ha,
                "percent_overlap": percent_overlap,
                "layer_area_ha": getattr(obj, "area_ha", None),
                "target_area_ha": self.target_area_ha,
                "intersection_geom": inter,
            })

        return results

    # -----------------------------------------------------------
    # Compute intersections across multiple layers
    # -----------------------------------------------------------
    def compute_all_layers(self, layers):
        """Execute intersection analysis for all given layers."""
        results = {}

        for layer in layers:
            name = layer.__name__
            intersec = self.compute_intersections(layer)

            if intersec:
                results[name] = intersec

        return results
