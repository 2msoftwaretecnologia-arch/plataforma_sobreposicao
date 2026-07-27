"""
Catálogo estático das bases de dados (camadas importadas de SHP) usadas na
análise de sobreposição, e de quais colunas de cada uma são efetivamente
extraídas pelo pipeline (ver `analysis/services/analyze_coordinates/overlap`).

Este arquivo é a fonte de exibição para o painel "Bases de Dados (SHP)".
Cada entrada espelha manualmente o que o respectivo Formatter
(`*/services/formatter/*.py`) devolve em `format()` — não há introspecção
automática porque essa lógica é definida em código, não em dados.

Se uma nova camada/SHP for adicionada (novo Model + Formatter), inclua aqui
a entrada correspondente para que ela apareça no painel.

Cada coluna extraída tem um campo "saida": é a chave que o Formatter
efetivamente devolve em `format()`. Quando "saida" é None, o valor só é usado
para montar o texto descritivo (item_info) e não existe como campo separado
no resultado — por isso não pode ser desligado individualmente no painel de
"Colunas no resultado da análise" (ver `toggleable_fields.py`).
"""

BASES_CONFIG = [
    {
        "modelo": "ZoningArea",
        "nome_base": "Base de Dados de Zoneamento",
        "tabela": "tb_area_zoneamento",
        "arquivo_upload": "zoning_zip_file",
        "cor": "#F57C00",
        "colunas_extraidas": [
            {"campo": "zone_name", "coluna_bd": "nome_zona", "rotulo": "Nome da Zona", "saida": "zona"},
            {"campo": "zone_acronym", "coluna_bd": "sigla_zona", "rotulo": "Sigla da Zona", "saida": "sigla"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "PhytoecologyArea",
        "nome_base": "Base de Dados de Fitoecologias",
        "tabela": "tb_area_fitoecologia",
        "arquivo_upload": "phytoecology_zip_file",
        "cor": "#6A1B9A",
        "colunas_extraidas": [
            {"campo": "phyto_name", "coluna_bd": "nome_fitoecologia", "rotulo": "Nome da Fitoecologia", "saida": "nome"},
        ],
        "campos_calculados": [
            "Área de interseção (ha)",
            "Área preservada (% da fitoecologia)",
            "Texto descritivo",
            "Geometria da interseção",
        ],
    },
    {
        "modelo": "EnvironmentalProtectionArea",
        "nome_base": "Base de Dados de APAs",
        "tabela": "tb_area_apa",
        "arquivo_upload": "environmental_protection_zip_file",
        "cor": "#C62828",
        "colunas_extraidas": [
            {"campo": "unit_name", "coluna_bd": "nome_unidade_conservacao", "rotulo": "Nome da Unidade", "saida": "unidade"},
            {"campo": "domains", "coluna_bd": "dominios", "rotulo": "Domínios", "saida": "dominios"},
            {"campo": "class_group", "coluna_bd": "grupo_classe", "rotulo": "Classe", "saida": "classe"},
            {"campo": "legal_basis", "coluna_bd": "fundo_legal", "rotulo": "Fundo Legal", "saida": "fundo_legal"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "IndigenousArea",
        "nome_base": "Base de Dados de Indígenas",
        "tabela": "tb_area_terra_indigena",
        "arquivo_upload": "indigenous_zip_file",
        "cor": "#8E24AA",
        "colunas_extraidas": [
            {"campo": "indigenous_name", "coluna_bd": "NOME_AREA", "rotulo": "Nome da Área", "saida": "nome_area"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "SicarRecord",
        "nome_base": "Base de Dados Sicar",
        "tabela": "tb_registro_sicar",
        "arquivo_upload": "sicar_zip_file",
        "cor": "#efff00",
        "colunas_extraidas": [
            {"campo": "car_number", "coluna_bd": "numero_car", "rotulo": "Número do CAR", "saida": None},
            {"campo": "status", "coluna_bd": "status", "rotulo": "Status", "saida": "status"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Quilombolas",
        "nome_base": "Base de Dados de Quilombolas",
        "tabela": "tb_area_quilombolas",
        "arquivo_upload": "quilombolas_zip_file",
        "cor": "#5D4037",
        "colunas_extraidas": [
            {"campo": "name", "coluna_bd": "nm_comunid", "rotulo": "Nome da Comunidade", "saida": "nome"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Paths",
        "nome_base": "Base de Dados de Veredas",
        "tabela": "tb_area_veredas",
        "arquivo_upload": "paths_zip_file",
        "cor": "#00897B",
        "colunas_extraidas": [
            {"campo": "hash_id", "coluna_bd": "hash_id", "rotulo": "Hash ID", "saida": "hash_id"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo (fixo: \"Vereda\")", "Geometria da interseção"],
    },
    {
        "modelo": "ConservationUnits",
        "nome_base": "Base de Dados de Unidades de Conservação",
        "tabela": "tb_area_unidades_conservacao",
        "arquivo_upload": "conservation_units_zip_file",
        "cor": "#388E3C",
        "colunas_extraidas": [
            {"campo": "unit", "coluna_bd": "Unidades", "rotulo": "Unidade", "saida": "unit"},
            {"campo": "domain", "coluna_bd": "Dominios", "rotulo": "Domínio", "saida": "domain"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "MunicipalBoundaries",
        "nome_base": "Base de Dados de Municípios",
        "tabela": "tb_area_municipios",
        "arquivo_upload": "municipal_boundaries_zip_file",
        "cor": "#1976D2",
        "colunas_extraidas": [
            {"campo": "name", "coluna_bd": "NOME", "rotulo": "Nome do Município", "saida": "name"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Sigef",
        "nome_base": "Base de Dados Sigef",
        "tabela": "tb_area_sigef",
        "arquivo_upload": "sigef_zip_file",
        "cor": "#D81B60",
        "colunas_extraidas": [
            {"campo": "name", "coluna_bd": "nome_area", "rotulo": "Nome da Área", "saida": "nome"},
            {"campo": "status", "coluna_bd": "status", "rotulo": "Status", "saida": "status"},
            {"campo": "property_code", "coluna_bd": "propriedade_co", "rotulo": "Código do Imóvel", "saida": None},
            {"campo": "installment_code", "coluna_bd": "codigo_imo", "rotulo": "Parcela", "saida": None},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Ruralsettlement",
        "nome_base": "Base de Dados de Assentamentos Rurais",
        "tabela": "tb_assentamento_rural",
        "arquivo_upload": "ruralsettlement_zip_file",
        "cor": "#00ACC1",
        "colunas_extraidas": [
            {"campo": "project_name", "coluna_bd": "nome_proje", "rotulo": "Nome do Projeto", "saida": "nome"},
            {"campo": "method_obtaining", "coluna_bd": "forma_obte", "rotulo": "Método de Obtenção", "saida": None},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "SnicTotal",
        "nome_base": "Base de Dados SNIC Total",
        "tabela": "tb_snic_total",
        "arquivo_upload": "snic_total_zip_file",
        "cor": "#EF6C00",
        "colunas_extraidas": [
            {"campo": "property_name", "coluna_bd": "nome_imove", "rotulo": "Nome do Imóvel", "saida": "nome"},
            {"campo": "property_code", "coluna_bd": "cod_imovel", "rotulo": "Código do Imóvel", "saida": None},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "DeforestationMapbiomas",
        "nome_base": "Base de Deforestação Mapbiomas",
        "tabela": "tb_area_deforestation_mapbiomas",
        "arquivo_upload": "deforestation_mapbiomas_zip_file",
        "cor": "#FF0000",
        "colunas_extraidas": [
            {"campo": "alert_code", "coluna_bd": "CODEALERTA", "rotulo": "Código do Alerta", "saida": "alert_code"},
            {"campo": "detection_year", "coluna_bd": "ANODETEC", "rotulo": "Ano de Detecção", "saida": "detection_year"},
            {"campo": "source", "coluna_bd": "source", "rotulo": "Fonte", "saida": "source"},
        ],
        "campos_calculados": [
            "Área de interseção (ha)",
            "Texto descritivo",
            "Link para o MapBiomas Alerta",
            "Geometria da interseção",
        ],
    },
    {
        "modelo": "Embargoes",
        "nome_base": "Base de Embargos do IBAMA",
        "tabela": "tb_embargoes",
        "arquivo_upload": "adm_embargos_ibama_a_zip_file",
        "cor": "#FF5722",
        "colunas_extraidas": [
            {"campo": "property_name", "coluna_bd": "nome_imove", "rotulo": "Nome do Imóvel", "saida": "property_name"},
            {"campo": "type_area", "coluna_bd": "tipo_area", "rotulo": "Tipo de Área", "saida": "type_area"},
            {"campo": "number_infraction_act", "coluna_bd": "num_auto_i", "rotulo": "Número do Auto de Infração", "saida": "number_infraction_act"},
            {"campo": "nome_embargado", "coluna_bd": "nome_embar", "rotulo": "Nome do Embargado", "saida": "nome_embargado"},
            {"campo": "cpf_cnpj_embargado", "coluna_bd": "cpf_cnpj_e", "rotulo": "CPF/CNPJ do Embargado", "saida": "cpf_cnpj_embargado"},
            {"campo": "control_unity", "coluna_bd": "unid_contr", "rotulo": "Unidade Controladora", "saida": "control_unity"},
            {"campo": "process_number", "coluna_bd": "num_process", "rotulo": "Número do Processo", "saida": "process_number"},
            {"campo": "act_description", "coluna_bd": "des_tad", "rotulo": "Descrição do Ato de Infração", "saida": "act_description"},
            {"campo": "infraction_description", "coluna_bd": "des_infrac", "rotulo": "Descrição da Infração", "saida": "infraction_description"},
            {"campo": "embargoe_date", "coluna_bd": "dat_embarg", "rotulo": "Data do Embargo", "saida": "embargoe_date"},
            {"campo": "priting_date", "coluna_bd": "dat_impres", "rotulo": "Data de Impressão", "saida": "priting_date"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Prodes",
        "nome_base": "Base de Dados Prodes",
        "tabela": "tb_prodes",
        "arquivo_upload": "prodes_zip_file",
        "cor": "#D84315",
        "colunas_extraidas": [
            {"campo": "identification", "coluna_bd": "main_class", "rotulo": "Identificação", "saida": "identificacao"},
            {"campo": "year", "coluna_bd": "year", "rotulo": "Ano", "saida": "ano"},
            {"campo": "satelite", "coluna_bd": "satelite", "rotulo": "Satélite", "saida": "satelite"},
            {"campo": "image_date", "coluna_bd": "image_date", "rotulo": "Data da Imagem", "saida": "data_da_imagem"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo", "Geometria da interseção"],
    },
    {
        "modelo": "Highways",
        "nome_base": "Base de Dados de Rodovias",
        "tabela": "tb_highways",
        "arquivo_upload": "highways_zip_file",
        "cor": "#9E9E9E",
        "colunas_extraidas": [
            {"campo": "NOME_2011", "coluna_bd": "NOME_2011", "rotulo": "Nome da Via", "saida": "NOME_2011"},
            {"campo": "CLAS_2011", "coluna_bd": "CLAS_2011", "rotulo": "Tipo da Via", "saida": "CLAS_2011"},
        ],
        "campos_calculados": ["Área de interseção (ha)", "Geometria da interseção"],
    },
    {
        "modelo": "Ipuca",
        "nome_base": "Base de Dados IPUCA",
        "tabela": "tb_ipuca",
        "arquivo_upload": "ipuca_zip_file",
        "cor": "#673AB7",
        "colunas_extraidas": [],
        "campos_calculados": ["Área de interseção (ha)", "Texto descritivo (fixo: \"Área IPUCA\")", "Geometria da interseção"],
    },
]


def get_bases_config():
    """Retorna o catálogo com contagens já calculadas para cada base."""
    bases = []
    for base in BASES_CONFIG:
        entry = dict(base)
        entry["total_colunas"] = len(base["colunas_extraidas"])
        bases.append(entry)
    return bases


def get_toggleable_fields(modelo):
    """Colunas da base `modelo` que existem como chave própria no resultado do
    Formatter (campo "saida" preenchido) — ou seja, que podem ser ligadas ou
    desligadas individualmente no resultado da análise de sobreposição.

    Colunas com "saida": None ficam de fora porque só existem embutidas no
    texto descritivo (item_info), não como campo separado.
    """
    base = next((b for b in BASES_CONFIG if b["modelo"] == modelo), None)
    if base is None:
        return []
    return [c for c in base["colunas_extraidas"] if c.get("saida")]
