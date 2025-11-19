from django.contrib.gis.geos import GEOSGeometry

class GeometryTarget:

    def __init__(self, geometry: GEOSGeometry):
        self.geometry = geometry
        self.area_m2, self.area_ha = self._compute_area(geometry)

    def _compute_area(self, geom):
        geom_utm = geom.transform(31982, clone=True)
        area_m2 = geom_utm.area
        return area_m2, area_m2 / 10000
