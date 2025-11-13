from typing import Any, Dict, List, Optional


def calculate_safe_overlap(
    verificador: Any,
    polygon_wkt: str,
    multipolygon_wkt: str,
) -> Optional[float]:
    try:
        return verificador.verificar_sobreposicao(
            polygon_wkt,
            multipolygon_wkt,
            "Polígono Grande",
            "MultiPolígono Pequeno",
        )
    except Exception:
        return None


def base_result(
    nome_base: str,
    areas_encontradas: List[Dict[str, Any]],
    quantidade_nao_avaliados: int,
) -> Dict[str, Any]:
    return {
        "nome_base": nome_base,
        "areas_encontradas": areas_encontradas,
        "quantidade_nao_avaliados": quantidade_nao_avaliados,
        "total_areas_com_sobreposicao": len(areas_encontradas),
    }