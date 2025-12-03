from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import Intersection
from django.db.models import F
import pandas as pd
from car_system.models import SicarRecord

UTM_SRID = 31982  # SIRGAS 2000 / UTM 22S
MIN_INTER_AREA_HA = 0.001  # Descartar intersecções muito pequenas
SICAR_FULL_OVERLAP_THRESHOLD = 98  # Descartar quando cobre ≥98% do polígono do SICAR


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
    # Query helpers
    # -----------------------------------------------------------
    def get_intersecting(self, layer_model):
        """
        Retorna um queryset de objetos da camada com interseção em relação ao alvo.
        Usa o campo `usable_geometry` para operações espaciais eficientes.
        """
        return layer_model.objects.filter(usable_geometry__intersects=self.target_geom)

    def _get_layer_area_m2(self, obj, fallback_geom=None):
        """
        Obtém a área da geometria da camada em m², priorizando campos pré-computados.
        Ordem de preferência: `area_m2` > `area_ha` > geometria transformada para UTM.
        """
        if getattr(obj, "area_m2", None):
            return obj.area_m2
        if getattr(obj, "area_ha", None):
            return obj.area_ha * 10000
        geom = getattr(obj, "usable_geometry", None) or fallback_geom
        if geom is None:
            return None
        try:
            return geom.transform(UTM_SRID, clone=True).area
        except Exception:
            return None

    def _compute_percent_overlap_layer(self, inter_area_m2, layer_area_m2):
        """
        Calcula o percentual de cobertura da intersecção sobre a área da camada.
        """
        if layer_area_m2 and layer_area_m2 > 0:
            return (inter_area_m2 / layer_area_m2) * 100
        return 0

    def _compute_percent_overlap_target(self, inter_area_m2):
        """
        Calcula o percentual de cobertura da intersecção sobre a área do alvo.
        """
        if self.target_area_m2 > 0:
            return (inter_area_m2 / self.target_area_m2) * 100
        return 0

    def _should_discard(self, layer_model, inter_area_ha, percent_overlap_layer):
        """
        Aplica regras de descarte:
        - Intersecções muito pequenas
        - Para SICAR, descarta quando a intersecção cobre ≥98% do polígono do SICAR
        """
        if inter_area_ha < MIN_INTER_AREA_HA:
            return True
        if layer_model is SicarRecord and percent_overlap_layer >= SICAR_FULL_OVERLAP_THRESHOLD:
            return True
        return False

    # -----------------------------------------------------------
    # Compute intersections
    # -----------------------------------------------------------
    def compute_intersections(self, layer_model):
        """
        Calcula intersecções entre o alvo e uma camada.
        1) Usa `usable_geometry` com Intersection (PostGIS)
        2) Fallback para `geometry` em texto quando necessário
        """
        results = self._compute_with_usable_geometry(layer_model)
        if results:
            return results
        return self._compute_with_fallback_geometry(layer_model)

    def _build_result_row(self, obj, inter, layer_model, fallback_geom=None):
        """
        Constrói o dicionário de saída para uma intersecção válida.
        Inclui métricas de área e percentuais de cobertura.
        """
        inter_utm = inter.transform(UTM_SRID, clone=True)
        inter_area_m2 = inter_utm.area
        inter_area_ha = inter_area_m2 / 10000

        layer_area_m2 = self._get_layer_area_m2(obj, fallback_geom=fallback_geom)
        percent_overlap_layer = self._compute_percent_overlap_layer(inter_area_m2, layer_area_m2)

        if self._should_discard(layer_model, inter_area_ha, percent_overlap_layer):
            return None

        percent_overlap_target = self._compute_percent_overlap_target(inter_area_m2)

        return {
            "id": obj.id,
            "intersection_area_m2": inter_area_m2,
            "intersection_area_ha": inter_area_ha,
            "percent_overlap": percent_overlap_target,
            "percent_overlap_layer": percent_overlap_layer,
            "layer_area_ha": getattr(obj, "area_ha", None),
            "target_area_ha": self.target_area_ha,
            "intersection_geom": inter,
        }

    def _compute_with_usable_geometry(self, layer_model):
        """
        Caminho principal: usa `usable_geometry` e a função `Intersection` para
        calcular intersecções diretamente via banco (PostGIS).
        """
        qs = (
            layer_model.objects
            .filter(usable_geometry__intersects=self.target_geom)
            .annotate(intersection=Intersection(F("usable_geometry"), self.target_geom))
        )

        results = []
        for obj in qs:
            inter = obj.intersection
            if inter.empty:
                continue
            row = self._build_result_row(obj, inter, layer_model)
            if row:
                results.append(row)
        return results

    def _compute_with_fallback_geometry(self, layer_model):
        """
        Caminho de fallback: quando não há `usable_geometry`, utiliza `geometry`
        em texto, normaliza SRID e calcula intersecção no app.
        """
        results = []
        for obj in layer_model.objects.exclude(geometry__isnull=True):
            try:
                geom = GEOSGeometry(getattr(obj, "geometry"), srid=4674)
            except Exception:
                continue
            if not geom.valid:
                try:
                    geom = geom.buffer(0)
                except Exception:
                    continue
            inter = geom.intersection(self.target_geom)
            if inter.empty:
                continue
            try:
                _ = inter.transform(UTM_SRID, clone=True)
            except Exception:
                continue
            row = self._build_result_row(obj, inter, layer_model, fallback_geom=geom)
            if row:
                results.append(row)
        return results

    # -----------------------------------------------------------
    # Compute intersections across multiple layers
    # -----------------------------------------------------------
    def compute_all_layers(self, layers):
        """
        Executa a análise de intersecção para todas as camadas fornecidas.
        Retorna um dicionário com os resultados por camada.
        """
        results = {}

        for layer in layers:
            name = layer.__name__
            intersec = self.compute_intersections(layer)

            if intersec:
                results[name] = intersec

        return results
