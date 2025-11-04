from core.read_files import (
    _carregar_dados_imoveis,
    _carregar_dados_zoneamento,
    _carregar_dados_fitoEcologias,
    _carregar_dados_apas,
)
from core.process_files import (
    _processar_base_dados_imoveis,
    _processar_base_dados_zoneamento,
    _processar_base_dados_fitoecologias,
    _processar_base_dados_apas,
)
from logica_sobreposicao import VerificadorSobreposicao
from core.manage_data import cache

def _get_verificador():
    """Retorna uma instância única do verificador"""
    if cache.cache_verificador is None:
        cache.cache_verificador = VerificadorSobreposicao()
    return cache.cache_verificador
    
def fazer_busca_completa(coordenadas, excluir_car=None): 
    """Versão que pesquisa em todas as bases de dados e identifica a origem dos resultados"""
    
    polygon_wkt = coordenadas
    verificador = _get_verificador()
    
    # Carregar dados de todas as bases
    print("Iniciando busca em todas as bases de dados...")
    
    dados_imoveis = _carregar_dados_imoveis(excluir_car)
    dados_zoneamento = _carregar_dados_zoneamento()
    dados_fito_ecologias = _carregar_dados_fitoEcologias()
    dados_apas = _carregar_dados_apas()
    
    # Processar cada base de dados
    resultados_por_base = []
    
    # Processar imóveis (usando função específica para dados com CAR)
    resultado_imoveis = _processar_base_dados_imoveis(
        polygon_wkt, dados_imoveis, "Base de Dados Sicar", verificador
    )
    resultados_por_base.append(resultado_imoveis)
    
    # Processar zoneamento
    resultado_zoneamento = _processar_base_dados_zoneamento(
        polygon_wkt, dados_zoneamento, "Base de Dados de Zoneamento", verificador
    )
    resultados_por_base.append(resultado_zoneamento)
    
    # Processar fitoecologias (usando função específica para preservar nomes)
    resultado_fito = _processar_base_dados_fitoecologias(
        polygon_wkt, dados_fito_ecologias, "Base de Dados de Fitoecologias", verificador
    )
    resultados_por_base.append(resultado_fito)
    
    # Processar APAs
    resultado_apas = _processar_base_dados_apas(
        polygon_wkt, dados_apas, "Base de Dados de APAs", verificador
    )
    resultados_por_base.append(resultado_apas)
    
    # Consolidar resultados
    todas_areas_encontradas = []
    total_nao_avaliados = 0
    total_sobreposicoes = 0
    
    for resultado in resultados_por_base:
        todas_areas_encontradas.extend(resultado['areas_encontradas'])
        total_nao_avaliados += resultado['quantidade_nao_avaliados']
        total_sobreposicoes += resultado['total_areas_com_sobreposicao']
    
    resultado_final = {
        'resultados_por_base': resultados_por_base,
        'areas_encontradas': todas_areas_encontradas,
        'quantidade_nao_avaliados': total_nao_avaliados,
        'total_areas_com_sobreposicao': total_sobreposicoes,
        'resumo_bases': {
            'imoveis': len(dados_imoveis),
            'zoneamento': len(dados_zoneamento),
            'fitoecologias': len(dados_fito_ecologias),
            'apas': len(dados_apas)
        }
    }
    
    print(f"Busca completa finalizada. Total de sobreposições encontradas: {total_sobreposicoes}")
    return resultado_final


# if __name__ == "__main__":
#     coordenadas = (
#         "POLYGON ((295342.27 8734305.23, 295389.91 8734125.99, 295414.47 8733995.33, 295419.01 8733931.01, 295407.73 8733823.71, 295410.84 8733784.24, 295408.71 8733658.89, 294756.63 8733390.84, 294604.62 8733756.92, 294688.84 8733819.59, 295342.27 8734305.23))"

#     )
#     teste = fazer_busca_completa(coordenadas)
#     print(teste)
