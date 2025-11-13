from typing import Any, Dict, List, Optional, Tuple
from environmental_layers.services.precess_data.common import (
    calculate_safe_overlap,
    base_result,
)


class ProtectionAreaProcess:
    def __init__(self, verifier: Any):
        """Inicializa com o verificador de sobreposição."""
        self.verifier = verifier

    def processar(
        self,
        polygon_wkt: str,
        apas_data: List[Dict[str, Any]],
        base_name: str,
    ) -> Dict[str, Any]:
        """Processa lista de APAs e retorna estrutura padronizada para UI."""
        if not apas_data:
            return base_result(base_name, [], 0)

        found_areas: List[Dict[str, Any]] = []
        not_evaluated_count = 0

        for apa_item in apas_data:
            try:
                item_result, not_eval_inc = self._process_protection_area_item(
                    polygon_wkt, apa_item, base_name
                )
                not_evaluated_count += not_eval_inc
                if item_result is not None:
                    found_areas.append(item_result)
            except Exception:
                # Em caso de erro inesperado, marcar item como não avaliado
                not_evaluated_count += 1
                continue

        return base_result(base_name, found_areas, not_evaluated_count)

    def _process_protection_area_item(
        self,
        polygon_wkt: str,
        apa_item: Dict[str, Any],
        base_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Processa um item de APA e decide se deve ser incluído no resultado."""
        multi_wkt = apa_item.get("wkt")
        overlap_hectares = calculate_safe_overlap(
            self.verifier, polygon_wkt, multi_wkt
        )

        if overlap_hectares is None:
            return None, 1
        if overlap_hectares <= 0:
            return None, 0

        return (
            self._build_result_item(base_name, apa_item, overlap_hectares),
            0,
        )

    def _build_result_item(
        self, base_name: str, apa_item: Dict[str, Any], overlap_hectares: float
    ) -> Dict[str, Any]:
        """Monta o dicionário do item de resultado para a UI."""
        return {
            "area": overlap_hectares,
            "unidade": apa_item.get("unidade"),
            "dominios": apa_item.get("dominios"),
            "classe": apa_item.get("classe"),
            "fundo_legal": apa_item.get("fundo_legal"),
        }