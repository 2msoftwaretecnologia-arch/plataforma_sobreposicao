from typing import Any, Dict, List, Optional, Tuple
from environmental_layers.services.precess_data.common import (
    calculate_safe_overlap,
    base_result,
)


class ZoningProcess:
    def __init__(self, verifier: Any):
        """Inicializa com o verificador de sobreposição."""
        self.verifier = verifier

    def processar(
        self,
        polygon_wkt: str,
        zoning_data: List[Dict[str, Any]],
        base_name: str,
    ) -> Dict[str, Any]:
        """Processa lista de zoneamentos e retorna estrutura padronizada para UI."""
        if not zoning_data:
            return base_result(base_name, [], 0)

        found_areas: List[Dict[str, Any]] = []
        not_evaluated_count = 0

        for zone_item in zoning_data:
            try:
                item_result, not_eval_inc = self._process_zone_item(
                    polygon_wkt, zone_item, base_name
                )
                not_evaluated_count += not_eval_inc
                if item_result is not None:
                    found_areas.append(item_result)
            except Exception:
                not_evaluated_count += 1
                continue

        return base_result(base_name, found_areas, not_evaluated_count)

    def _process_zone_item(
        self,
        polygon_wkt: str,
        zone_item: Dict[str, Any],
        base_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Processa um item de zoneamento e decide inclusão."""
        multi_wkt = zone_item.get("wkt")
        zone_name = zone_item.get("nome_zona")
        zone_acronym = zone_item.get("sigla_zona")

        overlap_hectares = calculate_safe_overlap(
            self.verifier, polygon_wkt, multi_wkt
        )

        if overlap_hectares is None:
            return None, 1
        if overlap_hectares <= 0:
            return None, 0

        return (
            self._build_result_item(zone_name, zone_acronym, overlap_hectares),
            0,
        )

    def _build_result_item(
        self, zone_name: Optional[str], zone_acronym: Optional[str], overlap_hectares: float
    ) -> Dict[str, Any]:
        """Monta o dicionário do item de resultado para a UI (mantém string esperada)."""
        return {
            "area": overlap_hectares,
            "item_info": f"Zonemaento: {zone_name} ({zone_acronym})",
        }