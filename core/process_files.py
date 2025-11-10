from cores_log import log_print, color_print
def _processar_base_dados_imoveis(polygon_wkt, dados_imoveis, nome_base, verificador):
    """Processa especificamente os dados dos imóveis que contêm tuplas (WKT, numero_car)"""
    from shapely.wkt import loads
    if not dados_imoveis:
        log_print(f"{nome_base}: nenhum registro de imóveis para processar.", level="WARNING", system="PROCESS_FILES")
        return {
            'nome_base': nome_base,
            'areas_encontradas': [],
            'quantidade_nao_avaliados': 0,
            'total_areas_com_sobreposicao': 0
        }
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for multipolygon_wkt, numero_car, status in dados_imoveis:
        try:
            area_sobreposicao = verificador.verificar_sobreposicao(
                polygon_wkt, 
                multipolygon_wkt, 
                "Polígono Grande", 
                "MultiPolígono Pequeno"
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                # Calcular a área total do CAR em hectares
                try:
                    geom_car = loads(multipolygon_wkt)
                    area_car_hectares = verificador._converter_para_hectares_otimizada(geom_car)
                except Exception:
                    area_car_hectares = 0

                # Regra: se sobreposição >= 98% da área do CAR, desconsiderar esse CAR
                incluir_resultado = True
                if area_car_hectares and area_car_hectares > 0:
                    percentual_sobreposicao = area_sobreposicao / area_car_hectares
                    if percentual_sobreposicao >= 0.98:
                        incluir_resultado = False

                if incluir_resultado:
                    areas_encontradas.append({
                        'area': area_sobreposicao,
                        'item_info': f"{nome_base} - CAR: {numero_car}",
                        'status': status
                    })
        except Exception as e:
            quantidade_nao_avaliados += 1
            log_print(f"{nome_base}: erro ao avaliar item: {e}", level="DEBUG", system="PROCESS_FILES")
            continue
    log_print(f"{nome_base}: {len(areas_encontradas)} sobreposições, {quantidade_nao_avaliados} não avaliados.", level="INFO", system="PROCESS_FILES")
    return {
        'nome_base': nome_base,
        'areas_encontradas': areas_encontradas,
        'quantidade_nao_avaliados': quantidade_nao_avaliados,
        'total_areas_com_sobreposicao': len(areas_encontradas)
    }
def _processar_base_dados_zoneamento(polygon_wkt, dados_imoveis, nome_base, verificador):
    """Processa especificamente os dados dos zoneamentos que contêm tuplas (WKT, numero_car)"""
    if not dados_imoveis:
        log_print(f"{nome_base}: nenhum registro de zoneamento para processar.", level="WARNING", system="PROCESS_FILES")
        return {
            'nome_base': nome_base,
            'areas_encontradas': [],
            'quantidade_nao_avaliados': 0,
            'total_areas_com_sobreposicao': 0
        }
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for multipolygon_wkt, nome_zoneamento, sigla_zoneamento in dados_imoveis:
        try:
            area_sobreposicao = verificador.verificar_sobreposicao(
                polygon_wkt, 
                multipolygon_wkt, 
                "Polígono Grande", 
                "MultiPolígono Pequeno"
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
            log_print(f"{nome_base}: erro ao avaliar item: {e}", level="DEBUG", system="PROCESS_FILES")
            continue
    log_print(f"{nome_base}: {len(areas_encontradas)} sobreposições, {quantidade_nao_avaliados} não avaliados.", level="INFO", system="PROCESS_FILES")
    return {
        'nome_base': nome_base,
        'areas_encontradas': areas_encontradas,
        'quantidade_nao_avaliados': quantidade_nao_avaliados,
        'total_areas_com_sobreposicao': len(areas_encontradas)
    }
def _processar_base_dados_fitoecologias(polygon_wkt, dados, nome_base, verificador):
    """Processa especificamente os dados de fitoecologias preservando o nome"""
    if not dados:
        log_print(f"{nome_base}: nenhum registro de fitoecologia para processar.", level="WARNING", system="PROCESS_FILES")
        return {
            'nome_base': nome_base,
            'areas_encontradas': [],
            'quantidade_nao_avaliados': 0,
            'total_areas_com_sobreposicao': 0
        }
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for multipolygon_wkt, nome_fitoecologia in dados:
        try:
            area_sobreposicao = verificador.verificar_sobreposicao(
                polygon_wkt, 
                multipolygon_wkt, 
                "Polígono Grande", 
                "MultiPolígono Pequeno"
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
            log_print(f"{nome_base}: erro ao avaliar item: {e}", level="DEBUG", system="PROCESS_FILES")
            continue
    log_print(f"{nome_base}: {len(areas_encontradas)} sobreposições, {quantidade_nao_avaliados} não avaliados.", level="INFO", system="PROCESS_FILES")
    return {
        'nome_base': nome_base,
        'areas_encontradas': areas_encontradas,
        'quantidade_nao_avaliados': quantidade_nao_avaliados,
        'total_areas_com_sobreposicao': len(areas_encontradas)
    }
def _processar_base_dados_apas(polygon_wkt, dados_apas, nome_base, verificador):
    """Processa especificamente os dados de APAs com informações detalhadas"""
    if not dados_apas:
        log_print(f"{nome_base}: nenhum registro de APAs para processar.", level="WARNING", system="PROCESS_FILES")
        return {
            'nome_base': nome_base,
            'areas_encontradas': [],
            'quantidade_nao_avaliados': 0,
            'total_areas_com_sobreposicao': 0
        }
    
    areas_encontradas = []
    quantidade_nao_avaliados = 0
    
    for i, apa_data in enumerate(dados_apas):
        try:
            # apa_data agora é um dicionário com wkt e informações adicionais
            multipolygon_wkt = apa_data['wkt']
            
            area_sobreposicao = verificador.verificar_sobreposicao(
                polygon_wkt, 
                multipolygon_wkt, 
                "Polígono Grande", 
                "MultiPolígono Pequeno"
            )
            
            if area_sobreposicao is None:
                quantidade_nao_avaliados += 1
            elif area_sobreposicao > 0:
                areas_encontradas.append({
                    'area': area_sobreposicao,
                    'unidade': apa_data['unidade'],
                    'dominios': apa_data['dominios'],
                    'classe': apa_data['classe'],
                    'fundo_legal': apa_data['fundo_legal']
                })
        except Exception as e:
            quantidade_nao_avaliados += 1
            log_print(f"{nome_base}: erro ao avaliar item {i}: {e}", level="DEBUG", system="PROCESS_FILES")
            continue
    log_print(f"{nome_base}: {len(areas_encontradas)} sobreposições, {quantidade_nao_avaliados} não avaliados.", level="INFO", system="PROCESS_FILES")
    return {
        'nome_base': nome_base,
        'areas_encontradas': areas_encontradas,
        'quantidade_nao_avaliados': quantidade_nao_avaliados,
        'total_areas_com_sobreposicao': len(areas_encontradas)
    }
