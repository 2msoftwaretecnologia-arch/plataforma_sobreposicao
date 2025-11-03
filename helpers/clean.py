from core.manage_data import cache
def limpar_cache():
    """Função para limpar todos os caches manualmente se necessário"""
   
    cache.cache_imoveis = None
    cache.cache_timestamp_imoveis = None
    cache.cache_zoneamento = None
    cache.cache_timestamp_zoneamento = None
    cache.cache_fito_ecologias = None
    cache.cache_timestamp_fito_ecologias = None
    cache.cache_apas = None
    cache.cache_timestamp_apas = None
    cache.cache_verificador = None
    print("Todos os caches foram limpos")