"""Monta o contexto do relatório impresso (`analysis/report_print.html`).

O relatório é lido por pessoas sem formação técnica (produtor, comprador,
gerente de banco). Por isso, além dos dados brutos, cada base recebe um
"guia" em linguagem simples e o topo do relatório traz um semáforo de
perguntas diretas com resposta e explicação.
"""
import json
import math
from functools import lru_cache

from shapely.geometry import shape

from analysis.services.view_services.bases_3d import MUNICIPIOS_JSON, TOCANTINS_GEOJSON
from analysis.services.view_services.land_use_service import comparar_uso_solo

# Níveis usados no relatório. A ordem define a ordem das seções.
ALERTA = 'alerta'        # problema sério, exige ação
ATENCAO = 'atencao'      # merece ser conferido
INFO = 'info'            # apenas informativo
NIVEL_ORDEM = {ALERTA: 0, ATENCAO: 1, INFO: 2}

# Cor do que foi encontrado nos mapas, igual ao semáforo do relatório
# (um pouco mais viva que a do texto, para aparecer sobre a imagem de satélite).
MAPA_CORES = {ALERTA: '#dc2626', ATENCAO: '#f59e0b', INFO: '#3b82f6'}

# Encostes menores que isso não acendem o semáforo (ver `limite_residual`).
TOLERANCIA_HA = 0.1
TOLERANCIA_PCT = 1.0

# Largura (px) do mapa de localização no Tocantins.
LOCALIZACAO_LARGURA = 200

# Ordem importa: o primeiro trecho contido no nome da base vence
# (ex.: "CAR Estadual" precisa vir antes de "CAR").
_BASE_GUIDE = (
    (('Embargos', 'Embargoes'), {
        'titulo': 'Embargos do IBAMA',
        'o_que_e': 'Áreas que o IBAMA proibiu de usar por causa de uma infração ambiental, como desmatar sem autorização.',
        'se_encontrado': 'Parte da propriedade está embargada. Nessa parte não se pode plantar, criar gado nem vender o que for produzido até a situação ser regularizada, e o embargo pode bloquear crédito rural.',
        'nivel': ALERTA,
    }),
    (('Mapbiomas', 'MapBiomas'), {
        'titulo': 'Alertas de desmatamento (MapBiomas)',
        'o_que_e': 'Avisos emitidos quando imagens de satélite mostram que a vegetação nativa foi retirada recentemente.',
        'se_encontrado': 'Foi detectada retirada de vegetação dentro da propriedade. É importante confirmar se havia autorização do órgão ambiental para isso.',
        'nivel': ALERTA,
    }),
    (('Indígenas', 'Indigenas'), {
        'titulo': 'Terras Indígenas',
        'o_que_e': 'Territórios reconhecidos pelo governo como de ocupação dos povos indígenas.',
        'se_encontrado': 'O desenho da propriedade avança sobre uma terra indígena. Essas terras pertencem à União e não podem ser ocupadas por particulares.',
        'nivel': ALERTA,
    }),
    (('Quilombolas',), {
        'titulo': 'Territórios Quilombolas',
        'o_que_e': 'Territórios reconhecidos de comunidades remanescentes de quilombos.',
        'se_encontrado': 'O desenho da propriedade avança sobre um território quilombola, o que pode indicar conflito de posse.',
        'nivel': ALERTA,
    }),
    (('Prodes',), {
        'titulo': 'Desmatamento registrado pelo governo (PRODES)',
        'o_que_e': 'Mapeamento oficial do INPE que registra, por satélite, as áreas desmatadas a cada ano.',
        'se_encontrado': 'O governo registrou desmatamento dentro da propriedade. Se aconteceu depois de 22/07/2008 e sem autorização, a área pode precisar ser recuperada.',
        'nivel': ATENCAO,
    }),
    (('Unidades de Conservação',), {
        'titulo': 'Unidades de Conservação',
        'o_que_e': 'Áreas protegidas por lei, como parques e reservas, criadas para preservar a natureza.',
        'se_encontrado': 'A propriedade está, total ou parcialmente, dentro de uma área protegida. Dependendo do tipo, o uso da terra tem regras extras ou pode ser proibido.',
        'nivel': ATENCAO,
    }),
    (('APAs',), {
        'titulo': 'Áreas de Proteção Ambiental (APA)',
        'o_que_e': 'Um tipo de área protegida onde é permitido morar e produzir, desde que se sigam regras ambientais próprias.',
        'se_encontrado': 'A propriedade está dentro de uma APA. É possível produzir, mas algumas atividades podem precisar de licença ambiental.',
        'nivel': ATENCAO,
    }),
    (('Assentamentos',), {
        'titulo': 'Assentamentos da Reforma Agrária',
        'o_que_e': 'Áreas destinadas pelo INCRA a famílias da reforma agrária.',
        'se_encontrado': 'Parte da propriedade coincide com um assentamento. Pode indicar conflito de limites ou de posse; vale conferir a documentação.',
        'nivel': ATENCAO,
    }),
    (('Veredas',), {
        'titulo': 'Veredas',
        'o_que_e': 'Áreas úmidas típicas do Cerrado, com buritis e nascentes, protegidas por lei.',
        'se_encontrado': 'Existem veredas na propriedade. Elas devem ser mantidas preservadas e não podem ser desmatadas.',
        'nivel': INFO,
    }),
    (('Hidrografia',), {
        'titulo': 'Rios e corpos d’água',
        'o_que_e': 'Rios, córregos, lagos e nascentes informados nos cadastros.',
        'se_encontrado': 'Há água na propriedade. As margens de rios e nascentes são Áreas de Preservação Permanente (APP) e precisam manter a vegetação.',
        'nivel': INFO,
    }),
    (('IPUCA',), {
        'titulo': 'Ipucas',
        'o_que_e': 'Matas naturais que ficam alagadas na época das chuvas, comuns na região do Araguaia. São protegidas.',
        'se_encontrado': 'Existem ipucas na propriedade. Essas áreas devem ser preservadas.',
        'nivel': INFO,
    }),
    (('CAR Estadual',), {
        'titulo': 'Cadastro Ambiental Rural estadual (base de 13/02/2023)',
        'o_que_e': 'Cadastros ambientais (CAR) feitos no sistema do Tocantins.',
        'se_encontrado': 'Existem cadastros de CAR no mesmo local. É normal aparecer o CAR da própria propriedade; cadastros de outras pessoas podem indicar sobreposição com vizinhos.',
        'nivel': INFO,
    }),
    (('Sicar', 'CAR'), {
        'titulo': 'Cadastro Ambiental Rural federal (SICAR)',
        'o_que_e': 'Registro ambiental obrigatório de todo imóvel rural, feito pelo próprio dono ou possuidor.',
        'se_encontrado': 'Existem cadastros de CAR no mesmo local. É normal aparecer o CAR da própria propriedade; cadastros de outras pessoas podem indicar sobreposição com vizinhos.',
        'nivel': INFO,
    }),
    (('Sigef',), {
        'titulo': 'Imóveis certificados pelo INCRA (SIGEF)',
        'o_que_e': 'Cadastro oficial de imóveis com limites medidos por GPS e certificados pelo INCRA.',
        'se_encontrado': 'Existem imóveis certificados no mesmo local. Se forem da própria propriedade, está tudo certo; se forem de outra pessoa, pode haver sobreposição de limites.',
        'nivel': INFO,
    }),
    (('SNIC',), {
        'titulo': 'Cadastro nacional de imóveis (SNIC)',
        'o_que_e': 'Cadastro de imóveis rurais mantido pelo governo federal.',
        'se_encontrado': 'Existem imóveis cadastrados no mesmo local. Confira se correspondem à própria propriedade.',
        'nivel': INFO,
    }),
    (('Zoneamento',), {
        'titulo': 'Zoneamento ecológico-econômico',
        'o_que_e': 'Mapa do Estado que indica para que tipo de uso cada região é mais adequada.',
        'se_encontrado': 'Mostra em qual zona a propriedade está e, com isso, que tipo de atividade é mais indicada para ela.',
        'nivel': INFO,
    }),
    (('Fitoecologias',), {
        'titulo': 'Vegetação natural e bioma',
        'o_que_e': 'Indica qual vegetação natural existe (ou existia) na área.',
        'se_encontrado': 'É o tipo de vegetação que define quanto da propriedade precisa ser mantido como Reserva Legal.',
        'nivel': INFO,
    }),
    (('Municípios', 'Municipios', 'Municpios'), {
        'titulo': 'Município',
        'o_que_e': 'Em qual município (ou municípios) a propriedade está.',
        'se_encontrado': '',
        'nivel': INFO,
    }),
    (('Rodovias',), {
        'titulo': 'Rodovias',
        'o_que_e': 'Estradas oficiais e suas faixas de domínio.',
        'se_encontrado': 'Uma rodovia passa pela propriedade. A faixa ao lado da estrada pertence ao poder público e tem uso restrito.',
        'nivel': INFO,
    }),
)


def base_guide(nome_base):
    """Guia em linguagem simples para a base (título, explicação e nível)."""
    nome_base = nome_base or ''
    for chaves, guia in _BASE_GUIDE:
        if any(chave in nome_base for chave in chaves):
            return guia
    nome = nome_base
    for prefixo in ('Base de Dados de ', 'Base de Dados ', 'Base de '):
        if nome.startswith(prefixo):
            nome = nome[len(prefixo):]
            break
    return {'titulo': nome, 'o_que_e': '', 'se_encontrado': '', 'nivel': INFO}


def _to_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _geojson(value):
    """GeoJSON como dict; as geometrias da análise chegam como texto."""
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _tocantins():
    """Contorno simplificado do Tocantins e a posição de Palmas, para o mapa de localização."""
    data = json.loads(TOCANTINS_GEOJSON.read_text(encoding='utf-8'))
    contorno = shape(data['features'][0]['geometry']).simplify(0.01)
    capital = None
    try:
        municipios = json.loads(MUNICIPIOS_JSON.read_text(encoding='utf-8'))
        capital = next((m for m in municipios if m.get('capital')), None)
    except (OSError, ValueError):
        pass
    return contorno, capital


def _coord_br(valor):
    return f'{valor:.5f}'.replace('.', ',')


def localizacao(propriedade_gj):
    """Coordenada central da propriedade e um mapinha (SVG) do Tocantins com o ponto.

    O SVG é montado aqui, e não com Leaflet, para sair igual na impressão
    mesmo sem internet para baixar imagens de mapa.
    """
    if not propriedade_gj:
        return None
    try:
        centro = shape(propriedade_gj).centroid
    except Exception:
        return None

    info = {
        'lat': _coord_br(centro.y),
        'lon': _coord_br(centro.x),
        'maps_url': f'https://www.google.com/maps?q={centro.y:.6f},{centro.x:.6f}',
        'svg': None,
    }

    try:
        contorno, capital = _tocantins()
    except (OSError, ValueError, KeyError):
        return info
    if not contorno.buffer(0.05).contains(centro):
        return info

    minx, miny, maxx, maxy = contorno.bounds
    # Projeção simples (equirretangular corrigida pela latitude média): no
    # tamanho de um mapinha, a distorção é imperceptível.
    k = math.cos(math.radians((miny + maxy) / 2))
    escala = LOCALIZACAO_LARGURA / ((maxx - minx) * k)

    def xy(lon, lat):
        return (lon - minx) * k * escala, (maxy - lat) * escala

    poligonos = getattr(contorno, 'geoms', [contorno])
    path = ' '.join(
        'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in (xy(*c[:2]) for c in p.exterior.coords)) + ' Z'
        for p in poligonos
    )
    px, py = xy(centro.x, centro.y)
    svg = {
        'largura': LOCALIZACAO_LARGURA,
        'altura': round((maxy - miny) * escala),
        'path': path,
        'x': round(px, 1),
        'y': round(py, 1),
        'capital': None,
    }
    if capital:
        cx, cy = xy(capital['lon'], capital['lat'])
        svg['capital'] = {'x': round(cx, 1), 'y': round(cy, 1), 'nome': capital['nome']}
    info['svg'] = svg
    return info


def _find_bases(bases, *chaves):
    return [b for b in bases if any(chave in (b.get('nome_base') or '') for chave in chaves)]


def limite_residual(tamanho_ha):
    """Área (ha) abaixo da qual um encoste é tratado como diferença de traçado.

    Cada base foi desenhada a partir de uma fonte e escala diferentes, então
    é comum dois polígonos vizinhos se encostarem em frações de hectare sem
    que exista conflito real. O limite é o menor entre `TOLERANCIA_HA` e
    `TOLERANCIA_PCT` da propriedade, para não esconder nada relevante em
    propriedades pequenas.
    """
    if tamanho_ha <= 0:
        return TOLERANCIA_HA
    return min(TOLERANCIA_HA, tamanho_ha * TOLERANCIA_PCT / 100)


def _check(pergunta, status, resposta, explicacao):
    return {'pergunta': pergunta, 'status': status, 'resposta': resposta, 'explicacao': explicacao}


def _overlap_check(bases, pergunta, nivel, resposta_sim, explicacao_sim, explicacao_nao, nomes=None):
    """Item do semáforo baseado em uma ou mais bases de sobreposição."""
    if not bases:
        return _check(pergunta, 'sem_dado', 'Não verificado',
                      'Esta base não estava disponível para a sua conta no momento da análise.')
    encontrados = [i for b in bases for i in b.get('areas_relevantes') or []]
    if not encontrados:
        if any(b.get('areas_residuais') for b in bases):
            explicacao_nao += (' Há apenas um encoste mínimo na divisa, que quase sempre é '
                               'diferença de desenho entre os mapas.')
        return _check(pergunta, 'ok', 'Não', explicacao_nao)
    detalhe = ''
    if nomes:
        chaves = nomes if isinstance(nomes, tuple) else (nomes,)
        valores = sorted({
            str(valor) for i in encontrados
            for valor in [next((i.get(c) for c in chaves if i.get(c)), None)] if valor
        })
        if valores:
            detalhe = ' — ' + ', '.join(valores)
    return _check(pergunta, nivel, resposta_sim + detalhe, explicacao_sim)


def _reserva_legal(resultado, demonstrativo, recibo):
    """Compara a Reserva Legal exigida (calculada pela vegetação) com a declarada no CAR."""
    exigida = _to_float(resultado.get('area_preservada_total'))
    declarada_num = None
    declarada_txt = None
    if demonstrativo:
        declarada_num = demonstrativo.get('area_reserva_legal_proposta_num')
        declarada_txt = demonstrativo.get('area_reserva_legal_proposta')
    elif recibo:
        declarada_txt = recibo.get('area_reserva_legal')

    deficit = None
    if declarada_num is not None:
        deficit = _to_float(declarada_num) - exigida

    return {
        'exigida': exigida,
        'declarada_num': declarada_num,
        'declarada_txt': declarada_txt,
        'tem_deficit': deficit is not None and deficit < 0,
        'deficit': abs(deficit) if deficit is not None and deficit < 0 else 0,
        'avaliada': deficit is not None,
    }


def _uso_solo_check(uso_solo, limite):
    """Item do semáforo do comparativo MapBiomas 2008 × ano atual."""
    pergunta = 'Houve retirada de vegetação nativa depois de 2008?'
    if not uso_solo or uso_solo.get('erro'):
        return _check(pergunta, 'sem_dado', 'Não verificado',
                      (uso_solo or {}).get('erro') or 'Não foi possível comparar os mapas do MapBiomas.')
    suprimida = uso_solo['suprimida']
    if suprimida < limite:
        return _check(
            pergunta, 'ok', 'Não',
            f"Pelos mapas do MapBiomas, a vegetação nativa de {uso_solo['ano_antes']} continua nativa "
            f"em {uso_solo['ano_depois']}.",
        )
    return _check(
        pergunta, ATENCAO, f'Sim — {_ha_br(suprimida)}',
        'Pelos mapas do MapBiomas, parte da vegetação nativa que existia em 2008 virou outro uso. '
        'Abertura depois de 22/07/2008 só é regular com autorização do órgão ambiental; sem ela, '
        'a área pode precisar ser recuperada. Veja a seção "Uso do solo: antes e agora".',
    )


def _ha_br(valor):
    return f'{valor:,.2f} ha'.replace(',', 'X').replace('.', ',').replace('X', '.')


def build_checklist(bases, rl, demonstrativo, recibo, uso_solo=None, limite=TOLERANCIA_HA):
    """Perguntas diretas do topo do relatório, cada uma com status de semáforo."""
    checks = [
        _overlap_check(
            _find_bases(bases, 'Embargos', 'Embargoes'),
            'A área tem embargo do IBAMA?', ALERTA, 'Sim',
            'Embargo é uma proibição de uso aplicada pelo IBAMA após uma infração ambiental. '
            'Enquanto durar, a parte embargada não pode ser usada para produzir.',
            'Não há embargo do IBAMA registrado dentro da área.',
        ),
        _overlap_check(
            _find_bases(bases, 'Mapbiomas', 'MapBiomas'),
            'Há alerta de desmatamento recente?', ALERTA, 'Sim',
            'Imagens de satélite mostraram retirada de vegetação nativa. '
            'É preciso confirmar se havia autorização do órgão ambiental.',
            'Nenhum alerta de desmatamento recente foi encontrado dentro da área.',
            nomes='detection_year',
        ),
        _overlap_check(
            _find_bases(bases, 'Prodes'),
            'O governo registrou desmatamento na área?', ATENCAO, 'Sim',
            'O PRODES (INPE) mapeou desmatamento dentro da propriedade. Desmatamentos antigos, '
            'anteriores a 22/07/2008, costumam ter tratamento mais brando na lei.',
            'O mapeamento oficial do governo (PRODES) não registrou desmatamento na área.',
            nomes='ano',
        ),
        _uso_solo_check(uso_solo, limite),
        _overlap_check(
            _find_bases(bases, 'Indígenas', 'Indigenas', 'Quilombolas'),
            'A área invade terra indígena ou quilombola?', ALERTA, 'Sim',
            'Essas terras são de comunidades tradicionais e não podem ser ocupadas por terceiros. '
            'Pode ser erro no desenho da área ou conflito real de posse.',
            'A área não alcança terras indígenas nem territórios quilombolas.',
        ),
        _overlap_check(
            _find_bases(bases, 'Unidades de Conservação', 'APAs'),
            'A área fica dentro de uma área protegida?', ATENCAO, 'Sim',
            'Áreas protegidas têm regras próprias de uso. Em APAs é possível produzir; '
            'em parques e reservas o uso pode ser proibido.',
            'A área não fica dentro de unidades de conservação nem de APAs.',
            nomes=('unidade', 'unit'),
        ),
    ]

    pergunta_rl = 'A Reserva Legal declarada é suficiente?'
    if rl['tem_deficit']:
        checks.append(_check(
            pergunta_rl, ALERTA, 'Não',
            'A área separada como Reserva Legal no CAR é menor do que a exigida para o tipo de '
            'vegetação da região. A diferença precisa ser recuperada ou compensada.',
        ))
    elif rl['avaliada']:
        checks.append(_check(
            pergunta_rl, 'ok', 'Sim',
            'A Reserva Legal declarada no CAR atende ao mínimo exigido para o tipo de vegetação da região.',
        ))
    else:
        checks.append(_check(
            pergunta_rl, 'sem_dado', 'Não avaliado',
            'Para esta conferência é preciso enviar o Demonstrativo do CAR junto com a análise.',
        ))

    pergunta_app = 'Há margem de rio ou nascente (APP) a recuperar?'
    fonte_app = demonstrativo or recibo
    if fonte_app and fonte_app.get('app_to_restore') and fonte_app.get('area_antropizada'):
        checks.append(_check(
            pergunta_app, ATENCAO, f"Sim — {fonte_app.get('area_antropizada')}",
            'Parte das Áreas de Preservação Permanente (margens de rios, nascentes) foi aberta '
            'depois de 22/07/2008 e precisa voltar a ter vegetação.',
        ))
    elif fonte_app:
        checks.append(_check(
            pergunta_app, 'ok', 'Não',
            'O CAR não indica Áreas de Preservação Permanente abertas que precisem ser recuperadas.',
        ))
    else:
        checks.append(_check(
            pergunta_app, 'sem_dado', 'Não avaliado',
            'Para esta conferência é preciso enviar o Recibo ou o Demonstrativo do CAR.',
        ))

    return checks


def _mapas_uso_solo(propriedade_gj, uso_solo):
    """Dados dos três mapas do comparativo (antes, depois e mudanças) no
    formato de `initReportMap`, com a imagem recortada por cima do satélite."""
    if not uso_solo or uso_solo.get('erro'):
        return None
    return {
        chave: {
            'propriedade': propriedade_gj, 'itens': [], 'cor': None,
            'imagem': {'url': url, 'bounds': uso_solo['bounds']},
        }
        for chave, url in uso_solo['imagens'].items()
    }


def build_report_context(data):
    """Enriquece `data` (resultado da análise) com tudo que o relatório precisa."""
    resultado = data.get('resultado') or {}
    demonstrativo = data.get('demonstrativo') or None
    recibo = data.get('recibo') or None
    tamanho = _to_float(resultado.get('tamanho_area'))

    limite = limite_residual(tamanho)
    propriedade_gj = _geojson(resultado.get('alvo_geojson'))

    bases = resultado.get('resultados_por_base') or []
    for base in bases:
        # Corpos d'água não são vegetação: tirá-los evita confundir a leitura do bioma.
        if 'Fitoecologias' in (base.get('nome_base') or ''):
            base['areas_encontradas'] = [
                item for item in base.get('areas_encontradas') or []
                if not any(p in (item.get('item_info') or '').lower() for p in ('água', 'agua'))
            ]
        areas = base.get('areas_encontradas') or []
        base['areas_relevantes'] = [i for i in areas if _to_float(i.get('area')) >= limite]
        base['areas_residuais'] = [i for i in areas if _to_float(i.get('area')) < limite]
        base['total_area'] = sum(_to_float(i.get('area')) for i in base['areas_relevantes'])
        base['total_residual'] = sum(_to_float(i.get('area')) for i in base['areas_residuais'])
        base['pct'] = min(base['total_area'] / tamanho * 100, 100) if tamanho else None
        base['guia'] = base_guide(base.get('nome_base'))
        base['cor_mapa'] = MAPA_CORES[base['guia']['nivel']]

        # Um único registro cobrindo a propriedade inteira desenharia só o
        # contorno pintado; nesse caso a frase "cobre toda a área" basta.
        base['cobre_tudo'] = len(base['areas_relevantes']) == 1 and (base['pct'] or 0) >= 99
        geometrias = [g for g in (_geojson(i.get('polygon_geojson')) for i in base['areas_relevantes']) if g]
        base['mapa'] = None
        if geometrias and not base['cobre_tudo']:
            base['mapa'] = {'propriedade': propriedade_gj, 'itens': geometrias, 'cor': base['cor_mapa']}

    com_ocorrencia = sorted(
        (b for b in bases if b['areas_relevantes']),
        key=lambda b: NIVEL_ORDEM[b['guia']['nivel']],
    )
    for n, base in enumerate(com_ocorrencia, start=1):
        base['json_id'] = f'map-base-data-{n}'
    so_residuais = [b for b in bases if not b['areas_relevantes'] and b['areas_residuais']]
    sem_ocorrencia = [b for b in bases if not b.get('areas_encontradas')]

    rl = _reserva_legal(resultado, demonstrativo, recibo)
    uso_solo = comparar_uso_solo(propriedade_gj, tamanho)
    checks = build_checklist(bases, rl, demonstrativo, recibo, uso_solo, limite)
    n_alertas = sum(1 for c in checks if c['status'] == ALERTA)
    n_atencao = sum(1 for c in checks if c['status'] == ATENCAO)
    if n_alertas:
        veredito = ALERTA
    elif n_atencao:
        veredito = ATENCAO
    else:
        veredito = 'ok'

    biomas = []
    for base in _find_bases(bases, 'Fitoecologias'):
        vistos = {}
        for item in base['areas_relevantes']:
            tipo = item.get('tipo') or item.get('item_info') or ''
            vistos[tipo] = vistos.get(tipo, 0) + _to_float(item.get('area'))
        biomas = [{'nome': nome, 'area': area} for nome, area in vistos.items() if nome]

    municipios = sorted({
        i.get('name') for b in _find_bases(bases, 'Municípios', 'Municipios', 'Municpios')
        for i in b['areas_relevantes'] if i.get('name')
    })

    data.update({
        'bases_com_ocorrencia': com_ocorrencia,
        'bases_so_residuais': so_residuais,
        'bases_sem_ocorrencia': sem_ocorrencia,
        'limite_residual': limite,
        'mapa_propriedade': {'propriedade': propriedade_gj, 'itens': [], 'cor': None} if propriedade_gj else None,
        'localizacao': localizacao(propriedade_gj),
        'checklist': checks,
        'n_alertas': n_alertas,
        'n_atencao': n_atencao,
        'veredito': veredito,
        'reserva_legal': rl,
        'uso_solo': uso_solo,
        'mapa_uso_solo': _mapas_uso_solo(propriedade_gj, uso_solo),
        'biomas': biomas,
        'municipios_encontrados': municipios,
        'nome_imovel': (recibo or {}).get('nome_imovel_rural') or '',
        'numero_car': (recibo or {}).get('car') or (demonstrativo or {}).get('car') or '',
        'proprietarios': (recibo or {}).get('proprietarios') or [],
    })
    return data
