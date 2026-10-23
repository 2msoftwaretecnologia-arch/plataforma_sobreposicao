"""CBERS-2B HRC (2,7 m, set/2007–mar/2010) do INPE no mapa de resultados,
com a posição corrigida pelo Landsat e cor pela fusão com o CCD (20 m) da
mesma passagem. Cobre o marco de 22/07/2008 do Código Florestal com ~11× o
detalhe do Landsat.

O nível 2 do INPE só tem correção sistemática: nas cenas testadas o HRC
estava ~2,5 km fora do lugar e o CCD ~1,5 km, o que inviabiliza sobrepor o
CAR. E os GeoTIFFs (~55 MB) não têm pirâmide nem blocos, então não dá para
gerar tiles direto da internet como no CBERS-4A. Por isso cada cena é baixada
e preparada uma vez no servidor (`hrc_prepare`, ~20–30 s: metade é o
download do INPE, que varia muito; o painel mostra a etapa e só começa
quando o usuário pede, depois de ver a miniatura):

1. o HRC é comparado por correlação de fase com uma cena Landsat 5/7
   Tier 1 (erro de ~12 m) perto da data, em blocos, e ganha um
   georreferenciamento afim novo (translação + rotação/escala);
2. o CCD do mesmo dia é alinhado ao HRC já corrigido e recortado na área
   dele (`ccd.tif`);
3. os parâmetros da fusão (método GSA: o pancromático é previsto pelas
   bandas do CCD por regressão e o que sobra, o detalhe fino, é somado a
   cada banda) e do contraste ficam no `meta.json`.

Depois disso os tiles saem do disco em ~30 ms. A fusão não inventa nada: a
forma vem do HRC e a cor do CCD, ambos captados no mesmo instante.
"""
import json
import logging
import math
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.contrib.gis.gdal import CoordTransform, GDALException, GDALRaster, OGRGeometry, SpatialReference
from django.contrib.gis.gdal.srs import AxisOrder
from django.contrib.gis.geos import GEOSException, GEOSGeometry, Polygon
from django.core.cache import cache

from analysis.services.view_services import image_enhance
from analysis.services.view_services import raster_tiles as rt
from analysis.services.view_services.imagery_service import (
    LANDSAT7_SLC_OFF_YEAR,
    LANDSAT_LEGACY_COLLECTION,
    LANDSAT_LEGACY_COMPOSITIONS,
    LANDSAT_LEGACY_MIN_SPAN,
    PC_BBOX_URL,
    PC_STAC_SEARCH,
    TIMEOUT,
    ImageryError,
    tile_bbox,
)

logger = logging.getLogger(__name__)

HRC_COLLECTION = 'CB2B-HRC-L2-DN-1'
CCD_COLLECTION = 'CB2B-CCD-L2-DN-1'
HRC_SCENE_RE = re.compile(r'^CBERS_2B_HRC_(\d{4})(\d{2})(\d{2})_(\d{3})_([A-E])_(\d{3})_(\d)_L2$')
# Os arquivos só vêm do acervo do INPE (o endereço sai do catálogo, nunca do navegador).
DATA_PREFIX = 'https://data.inpe.br/bdc/data/'
HRC_YEARS = (2007, 2010)
HRC_RES = 2.7
CCD_RES = 20
HRC_MIN_ZOOM = 12
HRC_SCENES_TTL = 6 * 60 * 60
# Margem da busca por ponto (graus, ~2 km): o contorno do catálogo tem o
# mesmo erro de posição da cena.
SEARCH_MARGIN = 0.02

COMPOSITIONS = {
    'pan': {'label': 'Pancromática (preto e branco)'},
    'cor': {'label': 'Cor natural (fusão HRC + CCD)', 'bands': (3, 2, 1)},
    'falsa_cor': {'label': 'Falsa cor (fusão, vegetação em vermelho)', 'bands': (4, 3, 2)},
}

DOWNLOAD_MAX_BYTES = 300 * 1024 * 1024
DOWNLOAD_TIMEOUT = (20, 120)
DOWNLOAD_CHUNK = 1024 * 1024
# Outro processo (uWSGI) preparando a mesma cena: espera por ele até isso.
PREPARE_LOCK_TTL = 15 * 60
PREPARE_WAIT = 150
PREPARE_POLL = 2
# Muda quando o meta.json ganha campos que os tiles passam a exigir, ou
# quando a preparação muda o resultado: cenas de versão antiga são refeitas.
# v2: a rotação da correção não era aplicada (o warp do Django copiava a
# rotação da cena para a grade de destino).
META_VERSION = 2

# Correção de posição. A correlação é feita numa grade de 20 m (o Landsat
# tem 30 m; mais fino não ganha precisão e fica mais lento).
REG_RES = 20.0
# Altura do pico da correlação em desvios-padrão: casamento real deu 60–220
# nos testes, ruído (bandas que não se parecem) ~13.
REG_MIN_PEAK = 25
REG_BLOCK_MIN_PEAK = 15
REG_BLOCKS = 4
REG_BLOCK_MIN_VALID = 0.5
REG_MIN_BLOCKS_AFFINE = 6
# Rotação/escala acima disso (1 %) não é erro de georreferenciamento: blocos
# mal casados. Fica só a translação.
REG_MAX_AFFINE_TERM = 0.01
REG_MAX_SHIFT_M = 8000
REF_MAX_DAYS = 400
REF_MAX_CLOUD = 20
REF_SLC_OFF_PENALTY = 15
REF_MIN_COVER = 0.6
# Pontos por fração do HRC fora da cena (10 % a menos ≈ 5 % a mais de nuvem).
REF_UNCOVERED_PENALTY = 50
REF_MARGIN = 0.01
# Abaixo disso a regressão do pancromático pelo CCD não explica a imagem
# (nuvem só numa delas, cena errada): sem fusão, só o pancromático.
FUSION_MIN_R2 = 0.3
# O CCD tem listras dos detectores (~5 px); a cor entra em baixa resolução
# (o detalhe vem do HRC), então um leve desfoque as some sem perder nitidez.
CCD_SMOOTH_SIGMA = 1.5
NATURAL_GAMMA = 1.25


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def _stac_search(url, body):
    try:
        response = requests.post(url, json=body, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning('Falha de conexão com o catálogo %s: %s', url, type(e).__name__)
        raise ImageryError('Catálogo de imagens indisponível.') from None
    if response.status_code != 200:
        raise ImageryError(f'Catálogo de imagens respondeu com erro {response.status_code}.')
    return response.json().get('features', [])


def _scene_name(scene):
    """'159_D_111_4' (órbita, câmera, ponto, subcena) do ID da cena."""
    match = HRC_SCENE_RE.match(scene)
    return '_'.join(match.groups()[3:]) if match else ''


def hrc_scenes(lon, lat):
    """Cenas HRC que cobrem o ponto, da mais recente à mais antiga."""
    key = f'raster:cbers2b:scenes:v2:{round(lon, 3)}:{round(lat, 3)}'
    scenes = cache.get(key)
    if scenes is None:
        m = SEARCH_MARGIN
        box = Polygon.from_bbox((lon - m, lat - m, lon + m, lat + m))
        features = _stac_search(rt.CBERS_STAC_SEARCH, {
            'collections': [HRC_COLLECTION],
            'intersects': json.loads(box.geojson),
            'limit': 200,
        })
        scenes = [
            {'id': f['id'], 'date': (f.get('properties', {}).get('datetime') or '')[:10], 'name': _scene_name(f['id']),
             'thumbnail': _thumbnail_href(f)}
            for f in features if HRC_SCENE_RE.match(f.get('id', ''))
        ]
        scenes.sort(key=lambda s: (s['date'], s['id']), reverse=True)
        cache.set(key, scenes, HRC_SCENES_TTL)
    return [{**s, 'ready': hrc_meta(s['id']) is not None} for s in scenes]


def _thumbnail_href(feature):
    """Miniatura do INPE (PNG de 512 px, antes da correção de posição), que o
    painel mostra antes de baixar a cena: dá para ver nuvem sem esperar."""
    href = (feature.get('assets', {}).get('thumbnail') or {}).get('href', '')
    return href if href.startswith(DATA_PREFIX) and href.endswith('.png') and '..' not in href else ''


def _stac_item(collection, item_id):
    features = _stac_search(rt.CBERS_STAC_SEARCH, {'collections': [collection], 'ids': [item_id]})
    if not features:
        raise ImageryError('Cena não encontrada no catálogo do INPE.')
    return features[0]


def _tif_href(asset):
    href = (asset or {}).get('href', '')
    if not href.startswith(DATA_PREFIX) or not href.endswith('.tif') or '..' in href:
        raise ImageryError('Arquivo da cena fora do acervo do INPE.')
    return href


def _ccd_item(hrc_item):
    """CCD do mesmo dia (mesma passagem do satélite) com mais área sobre o
    HRC, ou None se nenhum cobre pelo menos metade dele."""
    footprint = GEOSGeometry(json.dumps(hrc_item['geometry']))
    day = hrc_item['properties']['datetime'][:10]
    features = _stac_search(rt.CBERS_STAC_SEARCH, {
        'collections': [CCD_COLLECTION],
        'intersects': hrc_item['geometry'],
        'datetime': f'{day}T00:00:00Z/{day}T23:59:59Z',
        'limit': 20,
    })
    best, best_area = None, 0.5 * footprint.area
    for feature in features:
        geometry = feature.get('geometry') or json.loads(Polygon.from_bbox(feature['bbox']).geojson)
        area = GEOSGeometry(json.dumps(geometry)).intersection(footprint).area
        if area >= best_area:
            best, best_area = feature, area
    return best


def _ccd_band_hrefs(ccd_item):
    """{número da banda: URL} das bandas 1–4 (azul, verde, vermelho, NIR).
    O prefixo do asset (CCD1XS, CCD2XS) varia entre as bandas."""
    hrefs = {}
    for key, asset in ccd_item.get('assets', {}).items():
        match = re.search(r'BAND([1-4])$', key)
        if match:
            hrefs[int(match.group(1))] = _tif_href(asset)
    if set(hrefs) != {1, 2, 3, 4}:
        raise ImageryError('CCD sem as quatro bandas.')
    return hrefs


# ---------------------------------------------------------------------------
# Arquivos locais
# ---------------------------------------------------------------------------

def _cache_root():
    return Path(settings.IMAGERY_CACHE_DIR) / 'cbers2b'


def _scene_dir(scene):
    return _cache_root() / scene


def hrc_meta(scene):
    """Metadados da cena já preparada, ou None."""
    if not HRC_SCENE_RE.match(scene or ''):
        return None
    try:
        meta = json.loads((_scene_dir(scene) / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return meta if meta.get('version') == META_VERSION else None


def _download(url, path, progress=None):
    """Baixa `url` em `path`; `progress(baixado, total)` a cada ~4 MB."""
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            if response.status_code != 200:
                raise ImageryError(f'O INPE respondeu com erro {response.status_code} ao baixar a cena.')
            total = int(response.headers.get('Content-Length') or 0)
            size = 0
            with open(path, 'wb') as out:
                for chunk in response.iter_content(DOWNLOAD_CHUNK):
                    size += len(chunk)
                    if size > DOWNLOAD_MAX_BYTES:
                        raise ImageryError('Arquivo da cena maior que o esperado.')
                    out.write(chunk)
                    if progress and size % (4 * DOWNLOAD_CHUNK) < len(chunk):
                        progress(size, total)
    except requests.RequestException as e:
        logger.warning('Falha ao baixar %s: %s', url, type(e).__name__)
        raise ImageryError('Falha ao baixar a cena do INPE.') from None


def _dir_size(path):
    return sum(f.stat().st_size for f in path.iterdir() if f.is_file())


def _evict():
    """Apaga as cenas usadas há mais tempo (data do meta.json, renovada a
    cada `hrc_prepare`) enquanto o cache passa do limite."""
    root = _cache_root()
    limit = settings.IMAGERY_CACHE_MAX_MB * 1024 * 1024
    entries = []
    for scene_dir in root.iterdir() if root.exists() else []:
        meta = scene_dir / 'meta.json'
        if scene_dir.is_dir() and meta.exists():
            entries.append((meta.stat().st_mtime, scene_dir, _dir_size(scene_dir)))
    total = sum(size for _, _, size in entries)
    for _, scene_dir, size in sorted(entries, key=lambda e: e[0]):
        if total <= limit:
            break
        for name in ('hrc.tif', 'ccd.tif'):
            rt._forget(str(scene_dir / name))
        shutil.rmtree(scene_dir, ignore_errors=True)
        total -= size


# ---------------------------------------------------------------------------
# Correção de posição (correlação de fase)
# ---------------------------------------------------------------------------

def _fft_size(n):
    """Menor tamanho ≥ n só com fatores 2, 3 e 5: a FFT de 1687 px (7 × 241)
    leva ~10× a de 1728."""
    while True:
        m = n
        for p in (2, 3, 5):
            while m % p == 0:
                m //= p
        if m == 1:
            return n
        n += 1


def phase_shift(moving, fixed, mask):
    """(dy, dx, pico): o conteúdo do pixel (r, c) de `moving` está no pixel
    (r − dy, c − dx) de `fixed`. Subpixel por parábola no pico; `pico` é a
    altura dele em desvios-padrão da correlação (confiança do casamento)."""
    a = np.where(mask, moving - moving[mask].mean(), 0)
    b = np.where(mask, fixed - fixed[mask].mean(), 0)
    window = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    # O zero que completa o tamanho rápido não muda o pico (a janela já leva
    # as bordas a zero).
    shape = (_fft_size(a.shape[0]), _fft_size(a.shape[1]))
    spectrum = np.fft.rfft2(a * window, shape) * np.conj(np.fft.rfft2(b * window, shape))
    spectrum /= np.abs(spectrum) + 1e-9
    corr = np.fft.irfft2(spectrum, shape)
    iy, ix = np.unravel_index(np.argmax(corr), corr.shape)
    peak = corr[iy, ix] / (corr.std() or 1.0)

    def refine(minus, center, plus):
        denom = minus - 2 * center + plus
        return 0.0 if denom == 0 else 0.5 * (minus - plus) / denom

    h, w = corr.shape
    dy = iy + refine(corr[(iy - 1) % h, ix], corr[iy, ix], corr[(iy + 1) % h, ix])
    dx = ix + refine(corr[iy, (ix - 1) % w], corr[iy, ix], corr[iy, (ix + 1) % w])
    if dy > h / 2:
        dy -= h
    if dx > w / 2:
        dx -= w
    return float(dy), float(dx), float(peak)


def register(moving, fixed):
    """Ajuste afim (ou translação) que leva `moving` para a posição de
    `fixed` (mesma grade; 0 = sem dado), ou None se não casam.

    Primeiro o deslocamento global; depois o residual em REG_BLOCKS² blocos,
    que dá a rotação/escala. Devolve {'x': [a0, a1, a2], 'y': [...]} com o
    deslocamento em pixels da grade d(c, r) = a0 + a1·c + a2·r, mais o
    método, o número de blocos e o erro residual (px)."""
    mask = (moving > 0) & (fixed > 0)
    if mask.mean() < 0.2:
        return None
    dy0, dx0, peak = phase_shift(moving, fixed, mask)
    if peak < REG_MIN_PEAK or math.hypot(dy0, dx0) * REG_RES > REG_MAX_SHIFT_M:
        return None
    iy, ix = int(round(dy0)), int(round(dx0))
    shifted = np.roll(fixed, (iy, ix), axis=(0, 1))
    shifted_mask = np.roll(fixed > 0, (iy, ix), axis=(0, 1)) & (moving > 0)

    h, w = moving.shape
    bh, bw = h // REG_BLOCKS, w // REG_BLOCKS
    points = []
    for i in range(REG_BLOCKS):
        for j in range(REG_BLOCKS):
            sl = (slice(i * bh, (i + 1) * bh), slice(j * bw, (j + 1) * bw))
            if shifted_mask[sl].mean() < REG_BLOCK_MIN_VALID:
                continue
            ddy, ddx, block_peak = phase_shift(moving[sl], shifted[sl], shifted_mask[sl])
            if block_peak >= REG_BLOCK_MIN_PEAK and math.hypot(ddy, ddx) < 3:
                points.append(((j + 0.5) * bw, (i + 0.5) * bh, iy + ddy, ix + ddx))

    def translation(dy, dx, method):
        return {'x': [dx, 0.0, 0.0], 'y': [dy, 0.0, 0.0], 'method': method, 'blocks': len(points),
                'rms': None, 'peak': peak}

    if not points:
        return translation(dy0, dx0, 'translação')
    pts = np.array(points)
    if len(pts) < REG_MIN_BLOCKS_AFFINE:
        return translation(float(np.median(pts[:, 2])), float(np.median(pts[:, 3])), 'translação')

    design = np.column_stack([np.ones(len(pts)), pts[:, 0], pts[:, 1]])
    keep = np.ones(len(pts), dtype=bool)
    for _ in range(2):
        cx, *_ = np.linalg.lstsq(design[keep], pts[keep, 3], rcond=None)
        cy, *_ = np.linalg.lstsq(design[keep], pts[keep, 2], rcond=None)
        resid = np.hypot(design @ cx - pts[:, 3], design @ cy - pts[:, 2])
        rms = float(np.sqrt(np.mean(resid[keep] ** 2)))
        # Uma passada descartando blocos que não seguem o ajuste.
        new_keep = resid <= max(1.0, 2.5 * rms)
        if new_keep.sum() < REG_MIN_BLOCKS_AFFINE or (new_keep == keep).all():
            break
        keep = new_keep
    if max(abs(cx[1]), abs(cx[2]), abs(cy[1]), abs(cy[2])) > REG_MAX_AFFINE_TERM:
        return translation(float(np.median(pts[:, 2])), float(np.median(pts[:, 3])), 'translação')
    return {'x': [float(v) for v in cx], 'y': [float(v) for v in cy], 'method': 'afim',
            'blocks': int(keep.sum()), 'rms': rms, 'peak': peak}


def shift_at(fit, c, r):
    """(dy, dx) do ajuste no pixel (c, r) da grade."""
    return (fit['y'][0] + fit['y'][1] * c + fit['y'][2] * r,
            fit['x'][0] + fit['x'][1] * c + fit['x'][2] * r)


def corrected_geotransform(geotransform, grid, fit):
    """Geotransform GDAL novo (tupla de 6) com a correção `fit` medida na
    `grade`: o ponto (X, Y) passa para (X − res·dx, Y + res·dy), com o
    deslocamento d avaliado no pixel da grade onde (X, Y) cai. A correção é
    afim, então três cantos de pixel bastam."""
    ox, sx, rx, oy, ry, sy = geotransform
    gx, gy, res = grid['origin'][0], grid['origin'][1], grid['res']

    def correct(px, py):
        X, Y = ox + px * sx + py * rx, oy + px * ry + py * sy
        dy, dx = shift_at(fit, (X - gx) / res, (gy - Y) / res)
        return X - res * dx, Y + res * dy

    x0, y0 = correct(0, 0)
    x1, y1 = correct(1, 0)
    x2, y2 = correct(0, 1)
    return (x0, x1 - x0, x2 - x0, y0, y1 - y0, y2 - y0)


# ---------------------------------------------------------------------------
# Preparação da cena (roda na thread do GDAL de raster_tiles)
# ---------------------------------------------------------------------------

def _extent(raster):
    """(minx, miny, maxx, maxy) dos quatro cantos (vale com rotação)."""
    ox, sx, rx, oy, ry, sy = raster.geotransform
    corners = [(ox + i * sx + j * rx, oy + i * ry + j * sy)
               for i in (0, raster.width) for j in (0, raster.height)]
    xs, ys = zip(*corners)
    return min(xs), min(ys), max(xs), max(ys)


def _grid(extent, srid, res=REG_RES):
    minx, miny, maxx, maxy = extent
    return {'srid': srid, 'origin': (minx, maxy), 'res': res,
            'width': int(math.ceil((maxx - minx) / res)), 'height': int(math.ceil((maxy - miny) / res))}


def _resample(raster, grid, resampling, band=0):
    out = raster.warp({
        'driver': 'MEM', 'name': 'grade', 'srid': grid['srid'],
        'width': grid['width'], 'height': grid['height'],
        # Sem `skew` o Django copia a rotação da origem para a grade (e o HRC
        # corrigido tem rotação): a grade sairia girada junto com a cena.
        'origin': list(grid['origin']), 'scale': [grid['res'], -grid['res']], 'skew': [0, 0],
        'resampling': resampling,
    })
    return out.bands[band].data().astype(np.float32)


def _bounds(extent, srid, target):
    """Envelope (minx, miny, maxx, maxy) do retângulo `extent` em `target`."""
    minx, miny, maxx, maxy = extent
    polygon = OGRGeometry(f'POLYGON (({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))',
                          srs=SpatialReference(srid, axis_order=AxisOrder.TRADITIONAL))
    polygon.transform(CoordTransform(polygon.srs, SpatialReference(target, axis_order=AxisOrder.TRADITIONAL)))
    return list(polygon.extent)


def _overview(raster, res=REG_RES):
    """Cópia em memória do HRC reduzido a ~`res` m pela média de blocos (o 0
    não entra na média), com o mesmo georreferenciamento em escala.

    Reamostrar o arquivo de 13 500² px custa ~2,5 s por vez (LZW com uma
    linha por faixa); a correção e a fusão precisam dele umas cinco vezes.
    Lido uma vez aqui, cada reamostragem depois leva milissegundos."""
    ox, sx, rx, oy, ry, sy = raster.geotransform
    factor = max(1, int(round(res / abs(sx))))
    width, height = raster.width // factor, raster.height // factor
    band = raster.bands[0]
    out = np.zeros((height, width), np.float32)
    step = factor * 256  # linhas por leitura (~25 MB)
    for top in range(0, height * factor, step):
        rows = min(step, height * factor - top)
        block = band.data(offset=(0, top), size=(width * factor, rows)).astype(np.float32)
        block = block.reshape(rows // factor, factor, width, factor)
        valid = (block > 0).sum(axis=(1, 3))
        out[top // factor:(top + rows) // factor] = np.where(valid > 0, block.sum(axis=(1, 3)) / np.maximum(valid, 1), 0)
    small = GDALRaster({
        'driver': 'MEM', 'name': 'hrc20', 'srid': raster.srid, 'width': width, 'height': height,
        'datatype': 6, 'nr_of_bands': 1, 'bands': [{'data': out, 'nodata_value': 0}],
    })
    small.geotransform = [ox, sx * factor, rx * factor, oy, ry * factor, sy * factor]
    return small


def _reference_utm(path, hrc):
    """O recorte do Landsat (WGS84) reprojetado uma vez para a projeção do
    HRC, em 20 m, com margem para o erro de posição. Reprojetar de lat/lon
    custa ~0,7 s por vez; daqui em diante cada reamostragem é na mesma
    projeção (milissegundos)."""
    minx, miny, maxx, maxy = _extent(hrc)
    m = REG_MAX_SHIFT_M
    grid = _grid((minx - m, miny - m, maxx + m, maxy + m), hrc.srid)
    return GDALRaster(str(path)).warp({
        'driver': 'MEM', 'name': 'landsat', 'srid': grid['srid'],
        'width': grid['width'], 'height': grid['height'],
        'origin': list(grid['origin']), 'scale': [grid['res'], -grid['res']], 'skew': [0, 0],
        'resampling': 'Bilinear',
    })


def _register_hrc(hrc, small, ref, reference):
    """Corrige o georreferenciamento do HRC (`hrc` aberto para escrita, e a
    cópia reduzida `small`) pelo Landsat de referência (`ref`, já na
    projeção do HRC; `reference`, de onde veio). Devolve o resumo para o
    meta.json."""
    if ref is None:
        return {'ok': False, 'reason': 'Sem cena Landsat de referência com pouca nuvem perto da data.'}
    grid = _grid(_extent(hrc), hrc.srid)
    pan = _resample(small, grid, 'Bilinear')
    fit = register(pan, _resample(ref, grid, 'Bilinear'))
    if fit is None:
        return {'ok': False, 'reason': 'A cena não casou com o Landsat (nuvem ou mudança no terreno).'}
    hrc.geotransform = corrected_geotransform(hrc.geotransform, grid, fit)
    small.geotransform = corrected_geotransform(small.geotransform, grid, fit)
    dy, dx = shift_at(fit, grid['width'] / 2, grid['height'] / 2)
    # Conferência: refeita a grade, o deslocamento que sobra tem de ser ~0.
    check_grid = _grid(_extent(hrc), hrc.srid)
    pan_check = _resample(small, check_grid, 'Bilinear')
    ref_check = _resample(ref, check_grid, 'Bilinear')
    rdy, rdx, _ = phase_shift(pan_check, ref_check, (pan_check > 0) & (ref_check > 0))
    residual = math.hypot(rdy, rdx) * REG_RES
    if fit['rms'] is not None:
        residual = max(residual, fit['rms'] * REG_RES)
    return {
        'ok': True,
        'reference': {k: reference[k] for k in ('scene', 'date', 'platform')},
        'shift_m': round(math.hypot(dy, dx) * REG_RES),
        'residual_m': round(residual),
        'method': fit['method'],
        'blocks': fit['blocks'],
    }


def smooth(band, sigma):
    """Desfoque gaussiano (σ em pixels) que ignora o 0 (sem dado): a borda
    da cena não escurece. Separável, em numpy."""
    return smooth_bands([band], sigma)[0]


def smooth_bands(bands, sigma):
    """`smooth` de várias bandas com a mesma máscara (o pixel vale se todas
    têm dado), que é desfocada uma vez só."""
    radius = int(math.ceil(3 * sigma))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel = (kernel / kernel.sum()).astype(np.float32)

    def blur(a):
        # Soma de cópias deslocadas, um eixo por vez (o kernel tem ~11
        # termos), em float32: em float64 isso levava ~5 s nas 4 bandas.
        h, w = a.shape
        padded = np.pad(a, ((radius, radius), (0, 0)))
        out = np.zeros_like(a)
        for i, k in enumerate(kernel):
            out += k * padded[i:i + h]
        padded = np.pad(out, ((0, 0), (radius, radius)))
        out = np.zeros_like(a)
        for i, k in enumerate(kernel):
            out += k * padded[:, i:i + w]
        return out

    bands = [b.astype(np.float32) for b in bands]
    valid = np.all([b > 0 for b in bands], axis=0).astype(np.float32)
    weight = np.maximum(blur(valid), 1e-6)
    return [np.where(valid > 0, blur(b * valid) / weight, 0).astype(np.float32) for b in bands]


def _resample_bands(raster, grid, resampling):
    """Todas as bandas de `raster` na grade (um warp só)."""
    out = raster.warp({
        'driver': 'MEM', 'name': 'grade', 'srid': grid['srid'],
        'width': grid['width'], 'height': grid['height'],
        'origin': list(grid['origin']), 'scale': [grid['res'], -grid['res']], 'skew': [0, 0],
        'resampling': resampling,
    })
    return [band.data().astype(np.float32) for band in out.bands]


def _ccd_crop_gdal(hrefs, bbox):
    """As 4 bandas do CCD (MEM, uint8) recortadas na área do HRC (`bbox` em
    lon/lat do catálogo) mais a margem do erro de posição, lidas direto do
    INPE: o GeoTIFF tem uma linha por faixa, então só as linhas da área vêm
    pela rede (~40 % dos ~100 MB das quatro bandas)."""
    rt._configure_gdal()
    sources = [GDALRaster('/vsicurl/' + hrefs[b]) for b in (1, 2, 3, 4)]
    first = sources[0]
    ox, sx, rx, oy, ry, sy = first.geotransform
    if rx or ry or sy >= 0 or any(s.geotransform != first.geotransform or s.srid != first.srid for s in sources):
        raise ImageryError('Bandas do CCD em grades diferentes.')
    minx, miny, maxx, maxy = _bounds(bbox, 4326, first.srid)
    margin = REG_MAX_SHIFT_M + 2000
    left = max(0, int((minx - margin - ox) / sx))
    right = min(first.width, int(math.ceil((maxx + margin - ox) / sx)))
    top = max(0, int((oy - maxy - margin) / -sy))
    bottom = min(first.height, int(math.ceil((oy - miny + margin) / -sy)))
    if right <= left or bottom <= top:
        raise ImageryError('O CCD não cobre a cena.')
    width, height = right - left, bottom - top
    return GDALRaster({
        'driver': 'MEM', 'name': 'ccd', 'srid': first.srid, 'width': width, 'height': height,
        'origin': [ox + left * sx, oy + top * sy], 'scale': [sx, sy], 'datatype': 1, 'nr_of_bands': 4,
        'bands': [{'data': s.bands[0].data(offset=(left, top), size=(width, height)), 'nodata_value': 0}
                  for s in sources],
    })


def _build_ccd(hrc, small, ccd, out_path):
    """Alinha o CCD (`ccd`, recorte de 4 bandas em memória) ao HRC já
    corrigido (`small` é a cópia reduzida) e grava as 4 bandas na área do
    HRC, em 20 m. Devolve (resumo do alinhamento, grade) ou (motivo da
    falha, None)."""
    grid = _grid(_extent(hrc), hrc.srid, CCD_RES)
    pan = _resample(small, grid, 'Bilinear')
    bands = _resample_bands(ccd, grid, 'Bilinear')
    # O pancromático do HRC (0,50–0,80 µm) se parece mais com verde + vermelho.
    fit = register((bands[1] + bands[2]) / 2, pan)
    if fit is None:
        return {'ok': False, 'reason': 'O CCD não casou com o HRC.'}, None
    ccd.geotransform = corrected_geotransform(ccd.geotransform, grid, fit)
    out = GDALRaster({
        'driver': 'GTiff', 'name': str(out_path), 'srid': grid['srid'],
        'width': grid['width'], 'height': grid['height'],
        'origin': list(grid['origin']), 'scale': [grid['res'], -grid['res']],
        'datatype': 1, 'nr_of_bands': 4,
        # Sem isso a 4ª banda de 8 bits vira canal alfa e o warp a descarta.
        'papsz_options': {'compress': 'deflate', 'tiled': 'yes', 'photometric': 'minisblack', 'alpha': 'unspecified'},
    })
    for i, band in enumerate(smooth_bands(_resample_bands(ccd, grid, 'Bilinear'), CCD_SMOOTH_SIGMA)):
        out.bands[i].data(band.round().clip(0, 255).astype(np.uint8))
        out.bands[i].nodata_value = 0
    dy, dx = shift_at(fit, grid['width'] / 2, grid['height'] / 2)
    return {'ok': True, 'shift_m': round(math.hypot(dy, dx) * CCD_RES)}, grid


def fusion_params(pan, bands):
    """Parâmetros da fusão GSA na grade do CCD: `pan` (HRC reduzido a 20 m)
    e `bands` (B1..B4 do CCD), arrays alinhados com 0 = sem dado.

    I = a + Σ wₖ·Bₖ é o pancromático previsto pelas bandas; no tile, o
    detalhe P − I entra em cada banda com o ganho gₖ = cov(Bₖ, I)/var(I)."""
    valid = (pan > 0) & np.all([b > 0 for b in bands], axis=0)
    if valid.sum() < 1000:
        return None
    X = np.column_stack([np.ones(valid.sum())] + [b[valid].astype(np.float64) for b in bands])
    y = pan[valid].astype(np.float64)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    intensity = X @ coef
    r2 = 1 - ((y - intensity) ** 2).sum() / (((y - y.mean()) ** 2).sum() or 1.0)
    var = intensity.var() or 1.0
    gains = [float(np.mean((X[:, k + 1] - X[:, k + 1].mean()) * (intensity - intensity.mean())) / var)
             for k in range(len(bands))]
    stretch = [[float(v) for v in np.percentile(X[:, k + 1], (2, 98))] for k in range(len(bands))]
    return {'coef': [float(v) for v in coef], 'gains': gains, 'stretch': stretch, 'r2': float(r2)}


def natural_color_params(ccd_rgb, landsat_rgb):
    """Cor natural do CCD na escala do Landsat: o CCD do CBERS-2B não é
    calibrado entre bandas (o azul fica com mais véu e a imagem, roxa).

    Cada banda (B3, B2, B1) é levada à reflectância do Landsat (vermelho,
    verde, azul) igualando os percentis 5 e 95 na área comum, e daí ao
    mesmo contraste da camada Landsat realçada (piso comum no menor
    percentil 2, teto da composição natural, gamma). Devolve {'a', 'b',
    'gamma'}: o pixel da banda k vai a (a·valor + b) ** (1/gamma)."""
    valid = np.all([b > 0 for b in ccd_rgb + landsat_rgb], axis=0)
    if valid.sum() < 1000:
        return None
    _, base_hi = (float(v) for v in LANDSAT_LEGACY_COMPOSITIONS['natural']['rescale'].split(','))
    maps = []
    for ccd, landsat in zip(ccd_rgb, landsat_rgb):
        c5, c95 = np.percentile(ccd[valid], (5, 95))
        l5, l95 = np.percentile(landsat[valid], (5, 95))
        scale = (l95 - l5) / max(c95 - c5, 1.0)
        maps.append((scale, l5 - scale * c5))
    lo = min(float(np.percentile(landsat[valid], 2)) for landsat in landsat_rgb)
    lo = min(lo, base_hi - LANDSAT_LEGACY_MIN_SPAN)
    span = base_hi - lo
    return {'a': [s / span for s, _ in maps], 'b': [(o - lo) / span for _, o in maps], 'gamma': NATURAL_GAMMA}


def _process_gdal(work, reference, ccd, report=lambda text: None):
    """Corrige o HRC, monta o ccd.tif (de `ccd`, o recorte em memória, ou
    None) e calcula contraste e fusão. Todos os GDALRaster são fechados no
    fim (a pasta é renomeada depois). `report(texto)`: etapa para o painel."""
    rt._configure_gdal()
    report('Corrigindo a posição pelo Landsat…')
    hrc = GDALRaster(str(work / 'hrc.tif'), write=True)
    small = _overview(hrc)
    ref = _reference_utm(reference['path'], hrc) if reference else None
    meta = {'registration': _register_hrc(hrc, small, ref, reference)}

    pan = small.bands[0].data()
    meta['pan_stretch'] = [float(v) for v in np.percentile(pan[pan > 0], (2, 98))]
    extent = _extent(hrc)
    meta['bounds'] = _bounds(extent, hrc.srid, 4326)
    meta['bounds_3857'] = _bounds(extent, hrc.srid, 3857)

    meta['fusion'] = None
    if ccd is not None and meta['registration']['ok']:
        report('Alinhando a cor (CCD) ao HRC…')
        ccd_info, ccd_grid = _build_ccd(hrc, small, ccd, work / 'ccd.tif')
        meta['ccd_alignment'] = ccd_info
        if ccd_grid is not None:
            pan_ccd = _resample(small, ccd_grid, 'Bilinear')
            ccd = GDALRaster(str(work / 'ccd.tif'))
            ccd_bands = [ccd.bands[i].data().astype(np.float32) for i in range(4)]
            fusion = fusion_params(pan_ccd, ccd_bands)
            if fusion and fusion['r2'] >= FUSION_MIN_R2:
                if len(ref.bands) >= 3:
                    fusion['natural'] = natural_color_params(
                        [ccd_bands[2], ccd_bands[1], ccd_bands[0]], _resample_bands(ref, ccd_grid, 'Bilinear')[:3])
                meta['fusion'] = fusion
            else:
                meta['ccd_alignment'] = {'ok': False, 'reason': 'O CCD não explica o HRC (nuvem ou cena diferente).',
                                         'r2': fusion and round(fusion['r2'], 3)}
    elif ccd is not None:
        # Sem a posição do HRC corrigida, alinhar o CCD a ele não garante nada.
        meta['ccd_alignment'] = {'ok': False, 'reason': 'Posição do HRC não corrigida.'}
    meta['compositions'] = ['pan'] + (['cor', 'falsa_cor'] if meta['fusion'] else [])
    return meta


# ---------------------------------------------------------------------------
# Landsat de referência (Microsoft Planetary Computer)
# ---------------------------------------------------------------------------

def _landsat_reference(hrc_item, work):
    """Recorte RGB (GeoTIFF em WGS84, ~20 m) da cena Landsat
    5/7 Tier 1 mais próxima da data que cobre todo o HRC, ou None."""
    try:
        footprint = GEOSGeometry(json.dumps(hrc_item['geometry']))
        day = date.fromisoformat(hrc_item['properties']['datetime'][:10])
        features = _stac_search(PC_STAC_SEARCH, {
            'collections': [LANDSAT_LEGACY_COLLECTION],
            'intersects': hrc_item['geometry'],
            'datetime': f'{day - timedelta(days=REF_MAX_DAYS)}T00:00:00Z/{day + timedelta(days=REF_MAX_DAYS)}T23:59:59Z',
            'query': {'platform': {'in': ['landsat-5', 'landsat-7']}, 'eo:cloud_cover': {'lt': REF_MAX_CLOUD}},
            'fields': {'include': ['id', 'geometry', 'properties.datetime', 'properties.platform',
                                   'properties.eo:cloud_cover']},
            'limit': 200,
        })
        candidates = []
        for f in features:
            props = f.get('properties', {})
            # Tier 2 tem georreferenciamento pior: não serve de referência.
            if not f.get('id', '').endswith('_T1') or not f.get('geometry'):
                continue
            # Cena do HRC na divisa de duas órbitas do Landsat: nenhuma a
            # contém inteira. A correlação ignora a parte sem dado, então
            # basta cobrir boa parte, preferindo a que cobre mais.
            cover = GEOSGeometry(json.dumps(f['geometry'])).intersection(footprint).area / footprint.area
            if cover < REF_MIN_COVER:
                continue
            scene_day = date.fromisoformat(props['datetime'][:10])
            penalty = REF_SLC_OFF_PENALTY if props['platform'] == 'landsat-7' and scene_day.year >= LANDSAT7_SLC_OFF_YEAR else 0
            score = (abs((scene_day - day).days) / 30 + (props.get('eo:cloud_cover') or 0) + penalty
                     + (1 - cover) * REF_UNCOVERED_PENALTY)
            candidates.append((score, f['id'], scene_day.isoformat(), props['platform']))
        if not candidates:
            return None
        _, scene, scene_date, platform = min(candidates)

        minx, miny, maxx, maxy = footprint.extent
        minx, miny, maxx, maxy = minx - REF_MARGIN, miny - REF_MARGIN, maxx + REF_MARGIN, maxy + REF_MARGIN
        lat = math.radians((miny + maxy) / 2)
        width = int((maxx - minx) * 111320 * math.cos(lat) / REG_RES)
        height = int((maxy - miny) * 110574 / REG_RES)
        response = requests.get(
            PC_BBOX_URL.format(minx=minx, miny=miny, maxx=maxx, maxy=maxy, width=width, height=height),
            # Vermelho (correção de posição) + verde e azul (cor natural da fusão).
            # Sem a banda de máscara: o GDAL a toma por alfa e, num UInt16, o
            # 255 dela vira 0,4 % de opacidade (o warp divide tudo por 257).
            params={'collection': LANDSAT_LEGACY_COLLECTION, 'item': scene, 'assets': ['red', 'green', 'blue'],
                    'nodata': '0', 'return_mask': 'false'},
            timeout=DOWNLOAD_TIMEOUT)
        if response.status_code != 200 or not response.content.startswith((b'II*\x00', b'MM\x00*')):
            logger.warning('Recorte do Landsat %s falhou (status %s).', scene, response.status_code)
            return None
        path = work / 'landsat.tif'
        path.write_bytes(response.content)
        return {'path': path, 'scene': scene, 'date': scene_date, 'platform': platform}
    except (ImageryError, requests.RequestException, GEOSException, KeyError, ValueError) as e:
        logger.warning('Sem Landsat de referência para %s: %s', hrc_item.get('id'), type(e).__name__)
        return None


# ---------------------------------------------------------------------------
# Preparação (download + correção), chamada pela view
# ---------------------------------------------------------------------------

def hrc_prepare(scene):
    """Baixa e prepara a cena (ou reaproveita a já preparada) e devolve o
    meta. Bloqueia até terminar (~15–25 s na 1ª vez, a maior parte no
    download); com outro processo preparando a mesma cena, espera por ele.
    A etapa em andamento sai em `hrc_progress`."""
    if not HRC_SCENE_RE.match(scene or ''):
        raise ImageryError('Cena inválida.')
    meta = hrc_meta(scene)
    if meta is not None:
        os.utime(_scene_dir(scene) / 'meta.json')  # LRU do _evict
        return meta
    lock = f'raster:cbers2b:preparando:{scene}'
    if not cache.add(lock, 1, PREPARE_LOCK_TTL):
        deadline = time.monotonic() + PREPARE_WAIT
        while time.monotonic() < deadline:
            time.sleep(PREPARE_POLL)
            meta = hrc_meta(scene)
            if meta is not None:
                return meta
            if cache.get(lock) is None:
                break
        raise ImageryError('A cena ainda está sendo preparada. Tente de novo em instantes.')
    report = _progress_reporter(scene)
    try:
        return _prepare(scene, report)
    finally:
        cache.delete(lock)
        cache.delete(_progress_key(scene))


def _progress_key(scene):
    return f'raster:cbers2b:progresso:{scene}'


def _progress_reporter(scene):
    """Função que publica a etapa da preparação para `hrc_progress` (o
    painel consulta enquanto espera; no Redis vale entre processos)."""
    return lambda text: cache.set(_progress_key(scene), text, PREPARE_LOCK_TTL)


def hrc_progress(scene):
    """Etapa atual da preparação da cena, ou '' (parada ou já pronta)."""
    return cache.get(_progress_key(scene)) or ''


def _prepare(scene, report):
    report('Consultando o catálogo do INPE…')
    item = _stac_item(HRC_COLLECTION, scene)
    hrc_url = _tif_href(item.get('assets', {}).get('BAND1'))
    try:
        ccd_item = _ccd_item(item)
        ccd_hrefs = _ccd_band_hrefs(ccd_item) if ccd_item else {}
    except (ImageryError, GEOSException, KeyError) as e:
        logger.warning('Sem CCD para %s: %s', scene, e)
        ccd_item, ccd_hrefs = None, {}

    root = _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    work = root / f'{scene}.part'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()

    def downloaded(done, total):
        report(f'Baixando a cena do INPE ({done // 2 ** 20} de {total // 2 ** 20} MB)…' if total
               else f'Baixando a cena do INPE ({done // 2 ** 20} MB)…')

    try:
        # Em paralelo: HRC inteiro, recorte do Landsat e as linhas do CCD
        # que cobrem a cena (estas na thread do GDAL, por /vsicurl/).
        with ThreadPoolExecutor(max_workers=3) as pool:
            reference = pool.submit(_landsat_reference, item, work)
            hrc_job = pool.submit(_download, hrc_url, work / 'hrc.tif', downloaded)
            ccd_job = pool.submit(rt._in_gdal_thread, _ccd_crop_gdal, ccd_hrefs, item['bbox']) if ccd_hrefs else None
            hrc_job.result()
            ccd = None
            if ccd_job is not None:
                try:
                    ccd = ccd_job.result()
                except (ImageryError, GDALException) as e:
                    logger.warning('Sem o recorte do CCD para %s: %s', scene, e)
            reference = reference.result()

        try:
            meta = rt._in_gdal_thread(_process_gdal, work, reference, ccd, report)
        except GDALException:
            logger.exception('Falha ao processar a cena %s', scene)
            raise ImageryError('Falha ao processar a cena.') from None
        meta.update(version=META_VERSION, scene=scene, date=item['properties']['datetime'][:10],
                    ccd_scene=ccd_item['id'] if ccd_item and meta['fusion'] else None)
        del ccd  # o MEM do recorte (~25 MB) não precisa esperar o fim
        (work / 'landsat.tif').unlink(missing_ok=True)
        (work / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
        final = _scene_dir(scene)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(work, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    _evict()
    logger.info('Cena CBERS-2B %s preparada: %s', scene, meta['registration'])
    return meta


def hrc_client_info(meta):
    """O que o painel do mapa mostra da cena preparada."""
    registration = meta['registration']
    return {
        'scene': meta['scene'],
        'date': meta['date'],
        'compositions': [{'value': c, 'text': COMPOSITIONS[c]['label']} for c in meta['compositions']],
        'registration': {k: registration.get(k) for k in ('ok', 'reason', 'reference', 'shift_m', 'residual_m')},
        'fusion': bool(meta['fusion']),
        'fusion_note': None if meta['fusion'] else (meta.get('ccd_alignment') or {}).get('reason')
                       or 'Sem cena CCD do mesmo dia.',
    }


# ---------------------------------------------------------------------------
# Tiles
# ---------------------------------------------------------------------------

def _fuse(pan, bands, fusion, order):
    """RGB (uint8) da fusão GSA: cada banda do CCD (já ampliada ao tile)
    mais o detalhe do pancromático que as bandas não explicam."""
    coef, gains = fusion['coef'], fusion['gains']
    bands = [b.astype(np.float32) for b in bands]
    intensity = coef[0] + sum(coef[k + 1] * bands[k] for k in range(4))
    detail = pan.astype(np.float32) - intensity
    fused = {b: bands[b - 1] + gains[b - 1] * detail for b in order}
    natural = fusion.get('natural')
    if order == COMPOSITIONS['cor']['bands'] and natural:
        return np.dstack([
            (np.clip(natural['a'][i] * fused[b] + natural['b'][i], 0, 1) ** (1 / natural['gamma']) * 255).astype(np.uint8)
            for i, b in enumerate(order)
        ])
    return np.dstack([rt.stretch_band(fused[b], *fusion['stretch'][b - 1]) for b in order])


def hrc_tile(scene, composition, z, x, y, enhance=False):
    """(WEBP com transparência, content-type), ou None (cena não preparada,
    fora dela ou zoom abaixo do mínimo)."""
    if composition not in COMPOSITIONS or z < HRC_MIN_ZOOM:
        return None
    meta = hrc_meta(scene)
    if meta is None or composition not in meta['compositions']:
        return None
    minx, miny, maxx, maxy = tile_bbox(z, x, y)
    bminx, bminy, bmaxx, bmaxy = meta['bounds_3857']
    if maxx < bminx or minx > bmaxx or maxy < bminy or miny > bmaxy:
        return None
    key = f'raster:cbers2b:{scene}:{composition}:{"realce" if enhance else "padrao"}:{z}:{x}:{y}'
    webp = cache.get(key)
    if webp is not None:
        return webp, 'image/webp'

    hrc_path = str(_scene_dir(scene) / 'hrc.tif')
    # Afastado (pixel do tile bem maior que 2,7 m), média em vez de
    # interpolação: evita o serrilhado de pular pixels.
    reduce = image_enhance.tile_ground_pixel(z, y) > 2 * HRC_RES
    if enhance:
        radius = image_enhance.sharpen_radius(HRC_RES, z, y)
        buffer = image_enhance.sharpen_buffer(radius)
        pan = rt._warp_tile(hrc_path, z, x, y, 'Average' if reduce else 'Cubic', buffer)[0]
    else:
        radius = buffer = 0
        pan = rt._warp_tile(hrc_path, z, x, y, 'Average' if reduce else 'Bilinear')[0]
    if not pan.any():
        return None
    gray = rt.stretch_band(pan, *meta['pan_stretch'])
    rgb = np.dstack([gray, gray, gray])
    if composition != 'pan':
        bands = rt._warp_tile(str(_scene_dir(scene) / 'ccd.tif'), z, x, y, 'Bilinear', buffer)[:4]
        fused = _fuse(pan, bands, meta['fusion'], COMPOSITIONS[composition]['bands'])
        # Onde o CCD não cobre (borda da faixa), fica o pancromático.
        has_ccd = np.all([b > 0 for b in bands], axis=0)
        rgb = np.where(has_ccd[:, :, None], fused, rgb)
    alpha = np.where(pan > 0, 255, 0).astype(np.uint8)
    webp = rt.rgba_webp(np.dstack([rgb, alpha]), radius, buffer)
    cache.set(key, webp, rt.TILE_TTL)
    return webp, 'image/webp'
