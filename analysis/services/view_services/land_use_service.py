"""Comparativo do uso do solo dentro da propriedade entre 2008 e o ano mais
recente do MapBiomas, para o relatório impresso.

22/07/2008 é o marco do Código Florestal (Lei 12.651/2012): o que já estava
aberto antes dele é "área consolidada"; vegetação nativa retirada depois
precisa de autorização ou de recuperação. O MapBiomas tem um mapa por ano,
então 2008 é a referência mais próxima desse marco.

Os GeoTIFFs (30 m) são lidos só no retângulo da propriedade, recortados
pelo contorno, e o resultado (números e imagens) fica no cache.
"""
import base64
import hashlib
import io
import json
import logging
import math

import numpy as np
from django.core.cache import cache
from PIL import Image, ImageDraw
from shapely.geometry import shape

from analysis.services.view_services import raster_tiles as rt
from analysis.services.view_services.imagery_service import ImageryError

logger = logging.getLogger(__name__)

ANO_MARCO = 2008
CACHE_TTL = 30 * 24 * 60 * 60
CACHE_VERSION = 1

# Tamanho do pixel no chão: fino o bastante para o recorte seguir o contorno
# em propriedades pequenas, nunca mais grosso que o dado (30 m), e com um
# teto de pixels para propriedades enormes.
PIXEL_MIN_M = 5
PIXEL_MAX_M = 30
PIXELS_NO_LADO = 500
MAX_PIXELS = 2000

R_TERRA = 6378137.0

# Grupos para a leitura rápida. Afloramento rochoso, praia/duna e "não
# observado" ficam em "Outras áreas".
GRUPOS = (
    ('nativa', 'Vegetação nativa', '#1f8d49', {1, 3, 4, 5, 6, 10, 11, 12, 32, 49, 50}),
    ('agro', 'Agropecuária e silvicultura', '#e8c96a', {9, 14, 15, 18, 19, 20, 21, 35, 36, 39, 40, 41, 46, 47, 48, 62}),
    ('agua', 'Água', '#2532e4', {26, 31, 33}),
)
OUTRAS = ('outras', 'Outras áreas (urbana, mineração, solo exposto…)', '#9e9e9e')
NATIVA = GRUPOS[0][3]

# Mapa de mudanças: índice da paleta → (cor RGBA, rótulo).
MUDANCA_SUPRIMIDA = 1
MUDANCA_REGENERADA = 2
MUDANCA_NATIVA = 3
MUDANCA_USO = 4
MUDANCA_PALETA = {
    MUDANCA_SUPRIMIDA: (225, 29, 72, 255),
    MUDANCA_REGENERADA: (6, 182, 212, 255),
    MUDANCA_NATIVA: (31, 141, 73, 110),
    MUDANCA_USO: (245, 230, 184, 110),
}


def ano_atual():
    return rt.MAPBIOMAS_PRODUCTS['cobertura']['years'][1]


def _merc(lon, lat):
    x = R_TERRA * math.radians(lon)
    y = R_TERRA * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _lonlat(x, y):
    return math.degrees(x / R_TERRA), math.degrees(2 * math.atan(math.exp(y / R_TERRA)) - math.pi / 2)


def _poligonos(geom):
    if geom.geom_type == 'Polygon':
        return [geom]
    return [g for g in getattr(geom, 'geoms', []) if g.geom_type == 'Polygon']


def _janela(geom):
    """Origem (canto superior esquerdo, Mercator), tamanho do pixel no
    Mercator, largura e altura da janela que cobre a propriedade."""
    minlon, minlat, maxlon, maxlat = geom.bounds
    minx, miny = _merc(minlon, minlat)
    maxx, maxy = _merc(maxlon, maxlat)
    k = math.cos(math.radians((minlat + maxlat) / 2))
    lado_m = max(maxx - minx, maxy - miny) * k
    chao = min(PIXEL_MAX_M, max(PIXEL_MIN_M, lado_m / PIXELS_NO_LADO))
    pixel = chao / k
    # Um pixel de folga em volta, para o contorno não encostar na borda.
    minx, maxy = minx - pixel, maxy + pixel
    largura = math.ceil((maxx - minx) / pixel) + 1
    altura = math.ceil((maxy - miny) / pixel) + 1
    excesso = max(largura, altura) / MAX_PIXELS
    if excesso > 1:
        pixel *= excesso
        largura = math.ceil(largura / excesso)
        altura = math.ceil(altura / excesso)
    return (minx, maxy), pixel, largura, altura


def _mascara(geom, origem, pixel, largura, altura):
    """1 dentro da propriedade, 0 fora (buracos do polígono inclusos)."""
    img = Image.new('L', (largura, altura), 0)
    draw = ImageDraw.Draw(img)

    def px(coords):
        out = []
        for lon, lat in (c[:2] for c in coords):
            x, y = _merc(lon, lat)
            out.append(((x - origem[0]) / pixel, (origem[1] - y) / pixel))
        return out

    for poly in _poligonos(geom):
        draw.polygon(px(poly.exterior.coords), fill=1)
        for hole in poly.interiors:
            draw.polygon(px(hole.coords), fill=0)
    return np.asarray(img, dtype=bool)


def _peso_linhas(origem, pixel, altura):
    """Área no chão de um pixel de cada linha, relativa (cos² da latitude):
    no Mercator o pixel encolhe no chão conforme a latitude."""
    ys = origem[1] - (np.arange(altura) + 0.5) * pixel
    lats = np.degrees(2 * np.arctan(np.exp(ys / R_TERRA)) - np.pi / 2)
    return np.cos(np.radians(lats)) ** 2


def _png_data_uri(codes, paleta):
    """PNG paletado (o código é o índice da cor) como data URI. `paleta` é
    {código: (r, g, b[, a])}; códigos ausentes ficam transparentes."""
    rgb = bytearray(256 * 3)
    alpha = bytearray(256)
    for code, cor in paleta.items():
        rgb[code * 3:code * 3 + 3] = bytes(cor[:3])
        alpha[code] = cor[3] if len(cor) > 3 else 255
    codes = np.ascontiguousarray(codes, dtype=np.uint8)
    image = Image.frombytes('P', (codes.shape[1], codes.shape[0]), codes.tobytes())
    image.putpalette(bytes(rgb))
    out = io.BytesIO()
    image.save(out, format='PNG', transparency=bytes(alpha), optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode('ascii')


def _ler_ano(ano, origem, pixel, largura, altura):
    url = rt.MAPBIOMAS_PRODUCTS['cobertura']['url'].format(year=ano)
    return rt._warp_window(url, origem, pixel, largura, altura, 'NearestNeighbour')[0]


def _grupo(code):
    for chave, _, _, codigos in GRUPOS:
        if code in codigos:
            return chave
    return OUTRAS[0]


def _calcular(geom, tamanho_ha, anos):
    origem, pixel, largura, altura = _janela(geom)
    mascara = _mascara(geom, origem, pixel, largura, altura)
    if not mascara.any():
        return {'erro': 'A propriedade é pequena demais para o mapa de 30 m do MapBiomas.'}

    peso = mascara * _peso_linhas(origem, pixel, altura)[:, None]
    codigos = {ano: np.where(mascara, _ler_ano(ano, origem, pixel, largura, altura), 0) for ano in anos}

    # Área de cada pixel em ha, ajustada para a soma bater com o tamanho
    # calculado na análise (o recorte em pixels erra um pouco na borda).
    validos = peso * (codigos[anos[0]] > 0) * (codigos[anos[1]] > 0)
    total_peso = validos.sum()
    if total_peso <= 0:
        return {'erro': 'O MapBiomas não tem dados para esta área.'}
    if tamanho_ha and tamanho_ha > 0:
        ha_por_peso = tamanho_ha / total_peso
    else:
        ha_por_peso = (pixel ** 2) / 10000

    def area(sel):
        return float((validos * sel).sum() * ha_por_peso)

    nomes = {code: (nome, cor) for code, nome, cor in rt.MAPBIOMAS_CLASSES}
    presentes = set(np.unique(codigos[anos[0]]).tolist()) | set(np.unique(codigos[anos[1]]).tolist())
    presentes.discard(0)
    classes = []
    for code in presentes:
        a0 = area(codigos[anos[0]] == code)
        a1 = area(codigos[anos[1]] == code)
        if max(a0, a1) < 0.01:
            continue
        nome, cor = nomes.get(code, (f'Classe {code}', rt.UNKNOWN_CLASS_COLOR))
        classes.append({'codigo': code, 'nome': nome, 'cor': cor, 'antes': a0, 'depois': a1, 'variacao': a1 - a0})
    classes.sort(key=lambda c: max(c['antes'], c['depois']), reverse=True)

    grupos = []
    for chave, nome, cor in [g[:3] for g in GRUPOS] + [OUTRAS]:
        a0 = sum(c['antes'] for c in classes if _grupo(c['codigo']) == chave)
        a1 = sum(c['depois'] for c in classes if _grupo(c['codigo']) == chave)
        if max(a0, a1) >= 0.01:
            grupos.append({'chave': chave, 'nome': nome, 'cor': cor, 'antes': a0, 'depois': a1, 'variacao': a1 - a0})

    lista_nativa = list(NATIVA)
    nativa0 = np.isin(codigos[anos[0]], lista_nativa)
    nativa1 = np.isin(codigos[anos[1]], lista_nativa)
    tem_dado = (codigos[anos[0]] > 0) & (codigos[anos[1]] > 0)
    suprimida = tem_dado & nativa0 & ~nativa1
    regenerada = tem_dado & ~nativa0 & nativa1

    mudancas = np.zeros(mascara.shape, dtype=np.uint8)
    mudancas[tem_dado & nativa0 & nativa1] = MUDANCA_NATIVA
    mudancas[tem_dado & ~nativa0 & ~nativa1] = MUDANCA_USO
    mudancas[suprimida] = MUDANCA_SUPRIMIDA
    mudancas[regenerada] = MUDANCA_REGENERADA

    # Para onde foi a vegetação retirada (classe no ano atual).
    destino = []
    if suprimida.any():
        for code in np.unique(codigos[anos[1]][suprimida]).tolist():
            a = area(suprimida & (codigos[anos[1]] == code))
            if a >= 0.01:
                destino.append({'nome': nomes.get(code, (f'Classe {code}',))[0], 'area': a})
        destino.sort(key=lambda d: d['area'], reverse=True)

    paleta = {code: rt._hex_rgb(cor) for code, _, cor in rt.MAPBIOMAS_CLASSES}
    for code in presentes:
        paleta.setdefault(code, rt._hex_rgb(rt.UNKNOWN_CLASS_COLOR))

    oeste, norte = _lonlat(*origem)
    leste, sul = _lonlat(origem[0] + largura * pixel, origem[1] - altura * pixel)
    total = area(np.ones(mascara.shape, dtype=bool))

    def pct(valor):
        return valor / total * 100 if total else 0

    for linha in grupos + classes:
        linha['antes_pct'] = pct(linha['antes'])
        linha['depois_pct'] = pct(linha['depois'])
    nativa_antes, nativa_depois = area(nativa0), area(nativa1)
    area_suprimida, area_regenerada = area(suprimida), area(regenerada)
    return {
        'ano_antes': anos[0],
        'ano_depois': anos[1],
        'total': total,
        'classes': classes,
        'grupos': grupos,
        'nativa_antes': nativa_antes,
        'nativa_antes_pct': pct(nativa_antes),
        'nativa_depois': nativa_depois,
        'nativa_depois_pct': pct(nativa_depois),
        'suprimida': area_suprimida,
        'suprimida_pct': pct(area_suprimida),
        'regenerada': area_regenerada,
        'regenerada_pct': pct(area_regenerada),
        'destino_suprimida': destino,
        'bounds': [[sul, oeste], [norte, leste]],
        'imagens': {
            'antes': _png_data_uri(codigos[anos[0]], paleta),
            'depois': _png_data_uri(codigos[anos[1]], paleta),
            'mudancas': _png_data_uri(mudancas, MUDANCA_PALETA),
        },
    }


def comparar_uso_solo(propriedade_gj, tamanho_ha=None, ano_antes=ANO_MARCO, ano_depois=None):
    """Comparativo do uso do solo na propriedade entre `ano_antes` e
    `ano_depois` (padrão: 2008 e o ano mais recente). Em caso de falha,
    devolve {'erro': mensagem} para o relatório explicar a ausência."""
    if not propriedade_gj:
        return None
    ano_depois = ano_depois or ano_atual()
    chave = 'uso_solo:v{}:{}:{}:{}:{}'.format(
        CACHE_VERSION, ano_antes, ano_depois, round(tamanho_ha or 0, 4),
        hashlib.md5(json.dumps(propriedade_gj, sort_keys=True).encode()).hexdigest(),
    )
    resultado = cache.get(chave)
    if resultado is not None:
        return resultado
    try:
        geom = shape(propriedade_gj)
        if geom.is_empty:
            return None
        resultado = _calcular(geom, tamanho_ha, (ano_antes, ano_depois))
    except ImageryError:
        return {'erro': 'O MapBiomas não respondeu agora. Gere o relatório de novo em alguns minutos.'}
    except Exception:
        logger.exception('Falha no comparativo de uso do solo')
        return {'erro': 'Não foi possível calcular o comparativo de uso do solo.'}
    if 'erro' not in resultado:
        cache.set(chave, resultado, CACHE_TTL)
    return resultado
