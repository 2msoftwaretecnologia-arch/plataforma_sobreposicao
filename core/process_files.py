from typing import Any, Dict, List, Optional, Tuple
from shapely.wkt import loads
from helpers.funcoes_utils import deve_incluir_por_percentual


def _calcular_sobreposicao_segura(
    verificador: Any,
    polygon_wkt: str,
    multipolygon_wkt: str,
) -> Optional[float]:
    """Calcula a área de sobreposição (em hectares) de forma segura.

    - Retorna None em caso de erro inesperado.
    - Retorna 0 quando não há sobreposição significativa.
    """
    try:
        return verificador.verificar_sobreposicao(
            polygon_wkt,
            multipolygon_wkt,
            "Polígono Grande",
            "MultiPolígono Pequeno",
        )
    except Exception:
        return None


def _resultado_base(
    nome_base: str,
    areas_encontradas: List[Dict[str, Any]],
    quantidade_nao_avaliados: int,
) -> Dict[str, Any]:
    """Padroniza o dicionário de retorno das funções de processamento."""
    return {
        "nome_base": nome_base,
        "areas_encontradas": areas_encontradas,
        "quantidade_nao_avaliados": quantidade_nao_avaliados,
        "total_areas_com_sobreposicao": len(areas_encontradas),
    }


def _processar_base_dados_imoveis(
    polygon_wkt: str,
    dados_imoveis: List[Tuple[str, Any, Any]],
    nome_base: str,
    verificador: Any,
) -> Dict[str, Any]:
    """Processa dados dos imóveis (tuplas: (WKT, numero_car, status)).

    - Aplica regra de descarte quando sobreposição >= 98% da área total do CAR.
    - Retorna estrutura padronizada para consumo na UI.
    """
    if not dados_imoveis:
        return _resultado_base(nome_base, [], 0)
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for multipolygon_wkt, numero_car, status in dados_imoveis:
        try:
            area_sobreposicao = _calcular_sobreposicao_segura(
                verificador, polygon_wkt, multipolygon_wkt
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                # Calcular a área total do CAR em hectares
                try:
                    # Usa cache de geometria do verificador quando possível
                    geom_car = getattr(verificador, "_get_geometria_cached", loads)(multipolygon_wkt)
                    area_car_hectares = (
                        verificador._converter_para_hectares_otimizada(geom_car)
                        if geom_car is not None
                        else 0
                    )
                except Exception:
                    area_car_hectares = 0

                # Regra: desconsiderar quando percentual de sobreposição >= limite
                incluir_resultado = deve_incluir_por_percentual(
                    area_sobreposicao,
                    area_car_hectares,
                    0.98,
                )

                if incluir_resultado:
                    areas_encontradas.append({
                        'area': area_sobreposicao,
                        'item_info': f"{nome_base} - CAR: {numero_car}",
                        'status': status
                    })
        except Exception as e:
            quantidade_nao_avaliados += 1
            continue
    
    return _resultado_base(nome_base, areas_encontradas, quantidade_nao_avaliados)

def _processar_base_dados_zoneamento(
    polygon_wkt: str,
    dados_zoneamento: List[Dict[str, Any]],
    nome_base: str,
    verificador: Any,
) -> Dict[str, Any]:
    """Processa dados de zoneamento (lista de dicts: {'wkt','nome_zona','sigla_zona'})."""
    if not dados_zoneamento:
        return _resultado_base(nome_base, [], 0)
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for item in dados_zoneamento:
        try:
            multipolygon_wkt = item.get('wkt')
            nome_zoneamento = item.get('nome_zona')
            sigla_zoneamento = item.get('sigla_zona')

            area_sobreposicao = _calcular_sobreposicao_segura(
                verificador, polygon_wkt, multipolygon_wkt
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                areas_encontradas.append({
                    'area': area_sobreposicao,
                    'item_info': f"Zonemaento: {nome_zoneamento} ({sigla_zoneamento})",
                    
                })
        except Exception as e:
            quantidade_nao_avaliados += 1
            continue
    
    return _resultado_base(nome_base, areas_encontradas, quantidade_nao_avaliados)
def _processar_base_dados_fitoecologias(
    polygon_wkt: str,
    dados: List[Tuple[str, str]],
    nome_base: str,
    verificador: Any,
) -> Dict[str, Any]:
    """Processa dados de fitoecologias (tuplas: (WKT, nome_fitoecologia))."""
    if not dados:
        return _resultado_base(nome_base, [], 0)
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for multipolygon_wkt, nome_fitoecologia in dados:
        try:
            area_sobreposicao = _calcular_sobreposicao_segura(
                verificador, polygon_wkt, multipolygon_wkt
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                areas_encontradas.append({
                    'area': area_sobreposicao,
                    'item_info': f"Regioões FitoEcologicas: {nome_fitoecologia}"
                })
        except Exception as e:
            quantidade_nao_avaliados += 1
            continue
    
    return _resultado_base(nome_base, areas_encontradas, quantidade_nao_avaliados)
    
def _processar_base_dados_apas(
    polygon_wkt: str,
    dados_apas: List[Dict[str, Any]],
    nome_base: str,
    verificador: Any,
) -> Dict[str, Any]:
    """Processa dados de APAs (lista de dicts com campos específicos)."""
    if not dados_apas:
        return _resultado_base(nome_base, [], 0)
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for apa_data in dados_apas:
        try:
            # apa_data agora é um dicionário com wkt e informações adicionais
            multipolygon_wkt = apa_data.get('wkt')
            
            area_sobreposicao = _calcular_sobreposicao_segura(
                verificador, polygon_wkt, multipolygon_wkt
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                areas_encontradas.append({
                    'area': area_sobreposicao,
                    'unidade': apa_data.get('unidade'),
                    'dominios': apa_data.get('dominios'),
                    'classe': apa_data.get('classe'),
                    'fundo_legal': apa_data.get('fundo_legal'),
                })
        except Exception as e:
            quantidade_nao_avaliados += 1
            continue
    
    return _resultado_base(nome_base, areas_encontradas, quantidade_nao_avaliados)
