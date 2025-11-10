import os
from helpers.funcoes_utils import retornar_status_inteiro, retornar_lei
from core.manage_data import cache
import pandas as pd
from cores_log import log_print, color_print

def _carregar_dados_imoveis(excluir_car=None):
    
    
    caminho_csv = r"csvvv/conversao_imoveis__Sheet1.csv"

    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        log_print(f"Arquivo não encontrado: {caminho_csv}", level="ERROR", system="READ_FILES")
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)

    if cache.cache_imoveis is None or cache.cache_timestamp_imoveis != arquivo_modificado:
        log_print("Carregando dados dos imóveis...", level="INFO", system="READ_FILES")

        try:
            df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
            log_print("Arquivo CSV carregado com sucesso!", level="SUCCESS", system="READ_FILES")
        except Exception as e:
            log_print(f"Erro ao carregar CSV de imóveis: {e}", level="ERROR", system="READ_FILES")
            return []

        dados_imoveis = []
        total_rows = len(df.index)
        included = 0
        missing_geometry = 0
        missing_car = 0
        missing_status = 0
        # Espera colunas: geometry (WKT), cod_imovel (CAR), ind_status (string)
        for _, row in df.iterrows():
            coordenadas = row.get('geometry')
            numero_car = row.get('cod_imovel')
            status_str = row.get('ind_status')
            if not (isinstance(coordenadas, str) and coordenadas.strip()):
                missing_geometry += 1
                continue
            if numero_car is None or str(numero_car).strip() == "":
                missing_car += 1
            if status_str is None or str(status_str).strip() == "":
                missing_status += 1
            status = retornar_status_inteiro(status_str)
            dados_imoveis.append((coordenadas, numero_car, status))
            included += 1

        log_print(
            f"Imóveis: linhas={total_rows}, válidas={included}, descartadas_sem_geometry={missing_geometry}, campos_ausentes_car={missing_car}, campos_ausentes_status={missing_status}",
            level="INFO",
            system="READ_FILES",
        )

        cache.cache_imoveis = dados_imoveis
        cache.cache_timestamp_imoveis = arquivo_modificado
        log_print(f"Carregados {len(dados_imoveis)} imóveis em cache", level="INFO", system="READ_FILES")
    
    # Filtrar o CAR a ser excluído, se especificado
    dados_filtrados = cache.cache_imoveis
    if excluir_car and excluir_car.strip():
        dados_filtrados = [
            (coordenadas, car, status) for coordenadas, car, status in cache.cache_imoveis 
            if str(car) != str(excluir_car.strip())
        ]
        log_print(
            f"CAR {excluir_car} excluído da análise. Restaram {len(dados_filtrados)} imóveis.",
            level="INFO",
            system="READ_FILES",
        )
    
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
        log_print(f"Arquivo não encontrado: {caminho_csv}", level="ERROR", system="READ_FILES")
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)

    if cache.cache_zoneamento is None or cache.cache_timestamp_zoneamento != arquivo_modificado:
        log_print("Carregando dados dos zoenamentos...", level="INFO", system="READ_FILES")

        try:
            df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
            log_print("Arquivo CSV carregado com sucesso!", level="SUCCESS", system="READ_FILES")
        except Exception as e:
            log_print(f"Erro ao carregar CSV de imóveis: {e}", level="ERROR", system="READ_FILES")
            return []

        dados_zoneamento = []
        total_rows = len(df.index)
        included = 0
        missing_geometry = 0
        missing_nome = 0
        missing_sigla = 0
        for _, row in df.iterrows():
            coordenadas = row.get('geometry')
            nome_zona = row.get('nm_zona')
            Sigla_zona = row.get('zona_sigla')
            if not (isinstance(coordenadas, str) and coordenadas.strip()):
                missing_geometry += 1
                continue
            if nome_zona is None or str(nome_zona).strip() == "":
                missing_nome += 1
            if Sigla_zona is None or str(Sigla_zona).strip() == "":
                missing_sigla += 1
            dados_zoneamento.append((coordenadas, nome_zona, Sigla_zona))
            included += 1

        log_print(
            f"Zoneamento: linhas={total_rows}, válidas={included}, descartadas_sem_geometry={missing_geometry}, campos_ausentes_nome={missing_nome}, campos_ausentes_sigla={missing_sigla}",
            level="INFO",
            system="READ_FILES",
        )
        
        cache.cache_zoneamento = dados_zoneamento
        cache.cache_timestamp_zoneamento = arquivo_modificado
        log_print(f"Carregados {len(dados_zoneamento)} dados de zoneamento em cache", level="INFO", system="READ_FILES")
    
    return cache.cache_zoneamento
def _carregar_dados_fitoEcologias():
    """Carrega os dados de fitoecologias uma única vez e mantém em cache"""
    
    caminho_csv = r'csvvv/Fito_ecologias__Sheet1.csv'
    
    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        log_print(f"Arquivo não encontrado: {caminho_csv}", level="ERROR", system="READ_FILES")
        return []
    
    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(caminho_csv)
    
    if cache.cache_fito_ecologias is None or cache.cache_timestamp_fito_ecologias != arquivo_modificado:
        log_print("Carregando dados de fitoecologias...", level="INFO", system="READ_FILES")
        
        df = pd.read_csv(caminho_csv, sep=",", encoding="utf-8")
        log_print("Arquivo CSV carregado com sucesso!", level="SUCCESS", system="READ_FILES")
        
        dados_fito = []
        total_rows = len(df.index)
        included = 0
        missing_geometry = 0
        missing_nome = 0
        for _, row in df.iterrows():
            wkt = row.get('geometry')
            nome_fitoecologia = row.get('AnáliseCA')
            if not wkt:
                missing_geometry += 1
                continue
            if not nome_fitoecologia:
                missing_nome += 1
                continue
            dados_fito.append((wkt, nome_fitoecologia))
            included += 1

        log_print(
            f"Fitoecologias: linhas={total_rows}, válidas={included}, descartadas_sem_geometry={missing_geometry}, descartadas_sem_nome={missing_nome}",
            level="INFO",
            system="READ_FILES",
        )
        
        
        cache.cache_fito_ecologias = dados_fito
        cache.cache_timestamp_fito_ecologias = arquivo_modificado
        log_print(f"Carregados {len(dados_fito)} dados de fitoecologias em cache", level="INFO", system="READ_FILES")
    
    return cache.cache_fito_ecologias
def _carregar_dados_apas():
    """Carrega os dados de APAs uma única vez e mantém em cache"""
    
    arquivo_csv = r'csvvv/apas__Sheet1.csv'
    
   # Verificar se o arquivo existe
    if not os.path.exists(arquivo_csv):
        log_print(f"Arquivo não encontrado: {arquivo_csv}", level="ERROR", system="READ_FILES")
        return []

    # Verificar se precisa recarregar (arquivo foi modificado)
    arquivo_modificado = os.path.getmtime(arquivo_csv)
    
    if cache.cache_apas is None or cache.cache_timestamp_apas != arquivo_modificado:
        log_print("Carregando dados de APAs...", level="INFO", system="READ_FILES")
        
        df = pd.read_csv(arquivo_csv, sep=",", encoding="utf-8")
        log_print("Arquivo CSV carregado com sucesso!", level="SUCCESS", system="READ_FILES")
        
        dados_apas = []
        total_rows = len(df.index)
        included = 0
        missing_geometry = 0
        for _, row in df.iterrows():
            geom = row.get('geometry')
            if not geom:  # Verificar se tem dados WKT na coluna 10
                missing_geometry += 1
                continue
            unidade = row.get('Unidades')
            dominios = row.get('Dominios')
            classe = row.get('Classes')
            fundo_legal = retornar_lei(row.get('FundLegal'))
            dados_apas.append({
                'wkt': geom,
                'unidade': unidade,
                'dominios': dominios,
                'classe': classe,
                'fundo_legal': fundo_legal
            })
            included += 1

        log_print(
            f"APAs: linhas={total_rows}, válidas={included}, descartadas_sem_geometry={missing_geometry}",
            level="INFO",
            system="READ_FILES",
        )
        
       
        
        cache.cache_apas = dados_apas
        cache.cache_timestamp_apas = arquivo_modificado
        log_print(f"Carregados {len(dados_apas)} dados de APAs em cache", level="INFO", system="READ_FILES")
    
    return cache.cache_apas

