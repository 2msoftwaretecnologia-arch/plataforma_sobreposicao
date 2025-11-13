from typing import Any, Dict, List, Tuple, Optional
from environmental_layers.services.precess_data.common import (
    calcular_sobreposicao_segura,
    resultado_base,
)


class PhytoecologyProcess:
    def __init__(self, verifier: Any):
        """Inicializa com o verificador de sobreposição."""
        self.verifier = verifier

    def processar(
        self,
        polygon_wkt: str,
        phyto_data: List[Tuple[str, str]],
        base_name: str,
    ) -> Dict[str, Any]:
        """Processa lista de fitoecologias e retorna estrutura padronizada para UI."""
        if not phyto_data:
            return resultado_base(base_name, [], 0)

        found_areas: List[Dict[str, Any]] = []
        not_evaluated_count = 0

        for multi_wkt, phyto_name in phyto_data:
            try:
                item_result, not_eval_inc = self._process_phyto_item(
                    polygon_wkt, multi_wkt, phyto_name, base_name
                )
                not_evaluated_count += not_eval_inc
                if item_result is not None:
                    found_areas.append(item_result)
            except Exception:
                not_evaluated_count += 1
                continue

        return resultado_base(base_name, found_areas, not_evaluated_count)

    def _process_phyto_item(
        self,
        polygon_wkt: str,
        multi_wkt: str,
        phyto_name: str,
        base_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Processa um item de fitoecologia e decide inclusão."""
        overlap_hectares = calcular_sobreposicao_segura(
            self.verifier, polygon_wkt, multi_wkt
        )

        if overlap_hectares is None:
            return None, 1
        if overlap_hectares <= 0:
            return None, 0

        return (
            self._build_result_item(phyto_name, overlap_hectares),
            0,
        )

    def _build_result_item(self, phyto_name: str, overlap_hectares: float) -> Dict[str, Any]:
        """Monta o dicionário do item de resultado para a UI (mantém string esperada)."""
        return {
            "area": overlap_hectares,
            "item_info": f"Regioões FitoEcologicas: {phyto_name}",
        }