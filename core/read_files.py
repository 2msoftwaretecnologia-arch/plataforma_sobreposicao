import os
from helpers.funcoes_utils import retornar_status_inteiro, retornar_lei
from core.manage_data import cache
import pandas as pd

def _carregar_dados_imoveis(excluir_car=None):
    
    
    caminho_csv = r"csvvv/conversao_imoveis.csv"

    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)

    if cache.cache_imoveis is None or cache.cache_timestamp_imoveis != arquivo_modificado:
        print("Carregando dados dos imóveis...")

        try:
            df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
            print("✅ Arquivo CSV carregado com sucesso!\n")
        except Exception as e:
            print(f"Erro ao carregar CSV de imóveis: {e}")
            return []

        dados_imoveis = []
        # Espera colunas: geometry (WKT), cod_imovel (CAR), ind_status (string)
        for _, row in df.iterrows():
            coordenadas = row.get('geometry')
            numero_car = row.get('cod_imovel')
            status_str = row.get('ind_status')
            if isinstance(coordenadas, str) and coordenadas.strip():
                status = retornar_status_inteiro(status_str)
                dados_imoveis.append((coordenadas, numero_car, status))

        cache.cache_imoveis = dados_imoveis
        cache.cache_timestamp_imoveis = arquivo_modificado
        print(f"Carregados {len(dados_imoveis)} imóveis em cache")
    
    # Filtrar o CAR a ser excluído, se especificado
    dados_filtrados = cache.cache_imoveis
    if excluir_car and excluir_car.strip():
        dados_filtrados = [
            (coordenadas, car, status) for coordenadas, car, status in cache.cache_imoveis 
            if str(car) != str(excluir_car.strip())
        ]
        print(f"CAR {excluir_car} excluído da análise. Restaram {len(dados_filtrados)} imóveis.")
    
    return dados_filtrados


def _buscar_geometria_por_car(numero_car):
    """Retorna a geometria WKT do imóvel com o número do CAR informado.

    Usa o cache de imóveis se disponível; caso contrário, carrega os dados.
    """
    if numero_car is None or str(numero_car).strip() == "":
        return None

    # Garantir que o cache esteja populado
    if cache.cache_imoveis is None:
        _carregar_dados_imoveis()

    try:
        for coordenadas, car, _status in cache.cache_imoveis or []:
            if str(car).strip() == str(numero_car).strip():
                return coordenadas
    except Exception:
        pass

    # Se não encontrado em cache, tenta carregar novamente e buscar
    _carregar_dados_imoveis()
    try:
        for coordenadas, car, _status in cache.cache_imoveis or []:
            if str(car).strip() == str(numero_car).strip():
                return coordenadas
    except Exception:
        pass

    return None
def _carregar_dados_zoneamento():
    """Carrega os dados de zoneamento uma única vez e mantém em cache"""
    
    
    caminho_csv = r"csvvv/zoneamento__Sheet1.csv"

    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)

    if cache.cache_zoneamento is None or cache.cache_timestamp_zoneamento != arquivo_modificado:
        print("Carregando dados dos zoenamentos...")

        try:
            df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
            print("✅ Arquivo CSV carregado com sucesso!\n")
        except Exception as e:
            print(f"Erro ao carregar CSV de imóveis: {e}")
            return []

        dados_zoneamento = []
        for _, row in df.iterrows():
            coordenadas = row.get('geometry')
            nome_zona = row.get('nm_zona')
            Sigla_zona = row.get('zona_sigla')
            if isinstance(coordenadas, str) and coordenadas.strip():
                
                dados_zoneamento.append((coordenadas, nome_zona, Sigla_zona))
        
        cache.cache_zoneamento = dados_zoneamento
        cache.cache_timestamp_zoneamento = arquivo_modificado
        print(f"Carregados {len(dados_zoneamento)} dados de zoneamento em cache")
    
    return cache.cache_zoneamento
def _carregar_dados_fitoEcologias():
    """Carrega os dados de fitoecologias uma única vez e mantém em cache"""
    
    caminho_csv = r'csvvv/Fito_ecologias__Sheet1.csv'
    
    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        return []
    
    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)
    
    if cache.cache_fito_ecologias is None or cache.cache_timestamp_fito_ecologias != arquivo_modificado:
        print("Carregando dados de fitoecologias...")
        
        df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
        print("✅ Arquivo CSV carregado com sucesso!\n")
        
        dados_fito = []
        for _, row in df.iterrows():
            if row.get('geometry') and row.get('AnáliseCA'):  # Verificar se tem dados WKT na coluna 24
                wkt = row.get('geometry')
                nome_fitoecologia = row.get('AnáliseCA')
                dados_fito.append((wkt,nome_fitoecologia))
        
        
        cache.cache_fito_ecologias = dados_fito
        cache.cache_timestamp_fito_ecologias = arquivo_modificado
        print(f"Carregados {len(dados_fito)} dados de fitoecologias em cache")
    
    return cache.cache_fito_ecologias
def _carregar_dados_apas():
    """Carrega os dados de APAs uma única vez e mantém em cache"""
    
    arquivo_csv = r'csvvv/apas__Sheet1.csv'
    
   # Verificar se o arquivo existe
    if not os.path.exists(arquivo_csv):
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(arquivo_csv)
    
    if cache.cache_apas is None or cache.cache_timestamp_apas != arquivo_modificado:
        print("Carregando dados de APAs...")
        
        df = pd.read_csv(arquivo_csv, sep=",", encoding="utf-8")
        print("✅ Arquivo CSV carregado com sucesso!\n")
        
        dados_apas = []
        for _, row in df.iterrows():
            if row.get('geometry'):  # Verificar se tem dados WKT na coluna 10
                unidade = row.get('Unidades')
                dominios = row.get('Dominios')
                classe = row.get('Classes')
                fundo_legal = retornar_lei(row.get('FundLegal'))
                dados_apas.append({
                    'wkt': row.get('geometry'),
                    'unidade': unidade,
                    'dominios': dominios,
                    'classe': classe,
                    'fundo_legal': fundo_legal
                })
        
       
        
        cache.cache_apas = dados_apas
        cache.cache_timestamp_apas = arquivo_modificado
        print(f"Carregados {len(dados_apas)} dados de APAs em cache")
    
    return cache.cache_apas

