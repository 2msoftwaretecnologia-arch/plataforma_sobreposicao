from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.db.models.functions import Intersection
from django.db.models import F
import pandas as pd
UTM_SRID = 31982  # SIRGAS 2000 / UTM 22S – Tocantins


class SicarOverlapService:
    """
    Serviço responsável por verificar sobreposições entre um imóvel CAR
    e as camadas ambientais do banco, utilizando áreas pré-calculadas
    (area_m2 e area_ha) para máxima eficiência de processamento.
    """

    def __init__(self, car):
        self.car = car
        self.car_geom = car.geometry_new  # SRID 4674

        if self.car_geom is None:
            raise ValueError("O CAR informado não possui geometria válida.")

        # Área total do CAR (já calculada e armazenada no banco)
        self.area_car_m2 = car.area_m2
        self.area_car_ha = car.area_ha

    def verificar_em(self, layer_model):
        """Retorna queryset das áreas que intersectam o CAR."""
        return layer_model.objects.filter(
            geometry_new__intersects=self.car_geom
        )

    def calcular_intersecoes(self, layer_model):
        """
        Retorna lista de interseções entre o CAR e uma camada.
        Utiliza área do CAR e da camada pré-calculadas (campo area_m2/area_ha).
        Transforma APENAS a interseção para UTM para medir com precisão.
        """
        
        qs = (
            layer_model.objects
            .filter(geometry_new__intersects=self.car_geom)
            .annotate(inter=Intersection(F("geometry_new"), self.car_geom))
        )

        resultados = []

        for obj in qs:
            inter = obj.inter
            if inter.empty:
                continue

            # 🔥 Calcular área da interseção transformando apenas o INTER (dinâmico)
            inter_utm = inter.transform(UTM_SRID, clone=True)
            area_inter_m2 = inter_utm.area
            area_inter_ha = area_inter_m2 / 10000

            # 🔥 Percentual de sobreposição em relação ao CAR
            percentual = (
                (area_inter_m2 / self.area_car_m2) * 100
                if self.area_car_m2 > 0 else 0
            )

            resultados.append({
                "id": obj.id,
                "area_inter_ha": area_inter_ha,
                "percentual": percentual,
                "area_layer_ha": getattr(obj, "area_ha", None),
                "intersection_geom": inter,  # geometria original
                "area_car_ha": self.area_car_ha,
                "area_layer_ha": obj.area_ha,

            })
        df = pd.DataFrame(resultados)
        df.to_csv(f"intersecoes_{layer_model.__name__}.csv", index=False)
        return df

    def verificar_todas(self, layers):
        """Executa a análise para múltiplas camadas."""
        resultado = {}

        for layer in layers:
            nome = layer.__name__
            intersec = self.calcular_intersecoes(layer)

            if not intersec.empty:
                resultado[nome] = intersec

        return resultado
