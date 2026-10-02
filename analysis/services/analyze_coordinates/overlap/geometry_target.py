from django.contrib.gis.geos import GEOSGeometry

class GeometryTarget:

    def __init__(self, geometry: GEOSGeometry):
        self.geometry = geometry
        self.area_m2, self.area_ha = self._compute_area(geometry)
        # Registro de onde a geometria veio (CAR, parcela do SIGEF...): ele
        # não deve aparecer como sobreposição de si mesmo na própria camada.
        self.self_record = None

    def _compute_area(self, geom):
        geom_utm = geom.transform(31982, clone=True)
        area_m2 = geom_utm.area
        return area_m2, area_m2 / 10000
