from typing import Any, Dict, List, Tuple, Optional
from shapely.wkt import loads
from environmental_layers.services.precess_data.common import (
    calculate_safe_overlap,
    base_result,
)
from kernel.utils import should_include_by_percentage


class SicarProcess:
    def __init__(self, verifier: Any):
        """Inicializa com a instância responsável por verificar sobreposição."""
        self.verifier = verifier

    def process(
        self,
        polygon_wkt: str,
        properties_data: List[Dict[str, Any]],  
        base_name: str,
    ) -> Dict[str, Any]:
        """Processa a lista de imóveis, retornando o dicionário padronizado para a UI."""
        if not properties_data:
            return base_result(base_name, [], 0)

        found_areas: List[Dict[str, Any]] = []
        not_evaluated_count = 0

        for item in properties_data:
            multi_wkt = item.get("wkt")
            car_number = item.get("numero_car")
            car_status = item.get("sigla_zona")
            try:
                item_result, not_eval_inc = self._process_property_item(
                    polygon_wkt, multi_wkt, car_number, car_status, base_name
                )
                not_evaluated_count += not_eval_inc
                if item_result is not None:
                    found_areas.append(item_result)
            except Exception:
                # Em caso de erro inesperado ao processar o item, marcar como não avaliado
                not_evaluated_count += 1
                continue

        return base_result(base_name, found_areas, not_evaluated_count)

    def _process_property_item(
        self,
        polygon_wkt: str,
        multi_wkt: str,
        car_number: Any,
        car_status: Any,
        base_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Processa um único imóvel e retorna o item de resultado e o incremento de não avaliados."""
        overlap_hectares = calculate_safe_overlap(self.verifier, polygon_wkt, multi_wkt)

        if overlap_hectares is None:
            return None, 1
        if overlap_hectares <= 0:
            return None, 0

        car_area_hectares = self._get_car_area_hectares(multi_wkt)
        should_include = self._should_include_by_percentage(
            overlap_hectares, car_area_hectares, threshold=0.98
        )

        if not should_include:
            return None, 0

        return (
            self._build_result_item(base_name, car_number, car_status, overlap_hectares),
            0,
        )

    def _get_car_area_hectares(self, multi_wkt: str) -> float:
        """Calcula a área total do CAR em hectares a partir do WKT.

        Usa cache de geometrias do verificador quando disponível para desempenho.
        """
        try:
            car_geom = getattr(self.verifier, "_get_geometria_cached", loads)(multi_wkt)
            return (
                self.verifier._convert_to_hectares_optimized(car_geom)
                if car_geom is not None
                else 0
            )
        except Exception:
            return 0

    def _should_include_by_percentage(
        self, overlap_hectares: float, car_area_hectares: float, threshold: float
    ) -> bool:
        """Decide se deve incluir o item com base no percentual de sobreposição do CAR."""
        return should_include_by_percentage(overlap_hectares, car_area_hectares, threshold)

    def _build_result_item(
        self, base_name: str, car_number: Any, car_status: Any, overlap_hectares: float
    ) -> Dict[str, Any]:
        """Cria o dicionário do item de resultado conforme esperado pela UI."""
        return {
            "area": overlap_hectares,
            "item_info": f"{base_name} - CAR: {car_number}",
            "status": car_status,
        }