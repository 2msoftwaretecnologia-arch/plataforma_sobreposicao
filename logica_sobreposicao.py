from shapely.geometry import Polygon, MultiPolygon
from shapely.wkt import loads
import math

class VerificadorSobreposicao:
    def __init__(self):
        # Cache para geometrias já processadas
        self._cache_geometrias = {}
        # Pré-calcular constantes de conversão
        self.GRAU_PARA_METROS_LAT = 111320
        # Área mínima para considerar como sobreposição (em hectares)
        self.AREA_MINIMA_SOBREPOSICAO = 0.0001
    
    def verificar_sobreposicao(self, wkt1, wkt2, nome1="Polígono 1", nome2="Polígono 2"):
        """Verifica sobreposição entre duas geometrias WKT de forma otimizada"""
        try:
            # Usar cache para geometrias
            poly1 = self._get_geometria_cached(wkt1)
            poly2 = self._get_geometria_cached(wkt2)
            
            if poly1 is None or poly2 is None:
                return None
            
            # Verificação rápida de bounding box antes da interseção completa
            if not poly1.bounds_intersect(poly2):
                return 0
            
            # Verificar se há interseção
            if not poly1.intersects(poly2):
                return 0
            
            # Calcular área de sobreposição
            return self._calcular_area_sobreposicao_otimizada(poly1, poly2)
            
        except Exception as e:
            return None
    
    def _get_geometria_cached(self, wkt):
        """Obtém geometria do cache ou cria nova se necessário"""
        if wkt in self._cache_geometrias:
            return self._cache_geometrias[wkt]
        
        try:
            if not wkt or wkt.strip() == "":
                return None
            
            geometria = loads(wkt)
            
            if not geometria.is_valid:
                geometria = geometria.buffer(0)  # Tenta corrigir geometria inválida
                if not geometria.is_valid:
                    return None
            
            # Armazenar no cache (limitado a 1000 itens para evitar uso excessivo de memória)
            if len(self._cache_geometrias) < 1000:
                self._cache_geometrias[wkt] = geometria
            
            return geometria
            
        except Exception as e:
            return None
    
    def _calcular_area_sobreposicao_otimizada(self, poly1, poly2):
        """Versão otimizada do cálculo de área de sobreposição"""
        try:
            # Calcular interseção
            interseccao = poly1.intersection(poly2)
            
            if interseccao.is_empty:
                return 0
            
            # Converter para hectares de forma otimizada
            area_hectares = self._converter_para_hectares_otimizada(interseccao)
            
            # Verificar se a área é menor que o limite mínimo
            if area_hectares < self.AREA_MINIMA_SOBREPOSICAO:
                return 0
            
            return area_hectares
            
        except Exception as e:
            return 0
    
    def _converter_para_hectares_otimizada(self, geometria):
        """Versão otimizada da conversão para hectares"""
        try:
            # Usar centroid para latitude média
            centroid = geometria.centroid
            latitude_media = centroid.y
            
            # Cálculo otimizado dos fatores de conversão
            cos_lat = math.cos(math.radians(latitude_media))
            grau_para_metros_lon = self.GRAU_PARA_METROS_LAT * cos_lat
            
            area_graus = geometria.area
            area_metros = area_graus * self.GRAU_PARA_METROS_LAT * grau_para_metros_lon
            
            # Converter de metros quadrados para hectares (1 hectare = 10.000 m²)
            area_hectares = abs(area_metros) / 10000
            
            return area_hectares
        except:
            # Fallback simples - converter para hectares
            area_metros = geometria.area * self.GRAU_PARA_METROS_LAT * self.GRAU_PARA_METROS_LAT
            return area_metros / 10000
    
    def limpar_cache(self):
        """Limpa o cache de geometrias"""
        self._cache_geometrias.clear()

    # Método auxiliar para verificação rápida de bounds
    def bounds_intersect(self, geom1, geom2):
        """Verifica se os bounding boxes das geometrias se intersectam"""
        bounds1 = geom1.bounds
        bounds2 = geom2.bounds
        
        return not (bounds1[2] < bounds2[0] or bounds2[2] < bounds1[0] or 
                   bounds1[3] < bounds2[1] or bounds2[3] < bounds1[1])

# Adicionar método bounds_intersect às geometrias Shapely
Polygon.bounds_intersect = lambda self, other: VerificadorSobreposicao().bounds_intersect(self, other)
MultiPolygon.bounds_intersect = lambda self, other: VerificadorSobreposicao().bounds_intersect(self, other)

