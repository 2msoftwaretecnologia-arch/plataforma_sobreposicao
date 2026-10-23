"""Tiles gerados no servidor a partir de GeoTIFFs públicos lidos por HTTP
com o GDAL (/vsicurl/, só os blocos necessários): MapBiomas (uso do solo e
área queimada) e cenas CBERS-4A WPM (2 m) do Brazil Data Cube/INPE.

Os GeoTIFFs do MapBiomas (Coleção 11 e Fogo) não têm pirâmide de zoom: um
tile afastado leria gigabytes, então há zoom mínimo. Os tiles prontos ficam
no cache do Django (o dado de origem não muda).
"""
import atexit
import io
import logging
import queue
import re
import threading
from collections import OrderedDict
from ctypes import c_char_p

import numpy as np
import requests
from django.contrib.gis.gdal import CoordTransform, Driver, GDALException, GDALRaster, OGRGeometry, SpatialReference
from django.contrib.gis.gdal.libgdal import lgdal
from django.contrib.gis.gdal.srs import AxisOrder
from django.core.cache import cache
from PIL import Image

from analysis.services.view_services import image_enhance
from analysis.services.view_services.imagery_service import (
    TIMEOUT,
    ImageryError,
    tile_bbox,
)

logger = logging.getLogger(__name__)

TILE_SIZE = 256
TILE_TTL = 7 * 24 * 60 * 60

MAPBIOMAS_BUCKET = 'https://storage.googleapis.com/mapbiomas-public/initiatives/brasil'
MAPBIOMAS_PRODUCTS = {
    'cobertura': {
        'url': MAPBIOMAS_BUCKET + '/collection11/lulc/coverage/brazil_coverage/brazil_coverage-col11_{year}.tif',
        'years': (1985, 2025),
        'name': 'MapBiomas Coleção 11 – cobertura e uso da terra',
    },
    'fogo': {
        'url': MAPBIOMAS_BUCKET + '/collection_10/fire-col5/mapbiomas_fire_collection5_annual_burned_v1/burned_area_{year}.tif',
        'years': (1985, 2025),
        'name': 'MapBiomas Fogo Coleção 5 – área queimada anual',
    },
}
# Abaixo disso um tile cobre milhares de pixels de 30 m (GeoTIFF sem pirâmide).
MAPBIOMAS_MIN_ZOOM = 10

# Legenda oficial da Coleção 10 (a 11 mantém os códigos): código, nome, cor.
MAPBIOMAS_CLASSES = [
    (3, 'Formação Florestal', '#1f8d49'),
    (4, 'Formação Savânica', '#7dc975'),
    (5, 'Mangue', '#04381d'),
    (6, 'Floresta Alagável', '#007785'),
    (49, 'Restinga Arbórea', '#02d659'),
    (11, 'Campo Alagado e Área Pantanosa', '#519799'),
    (12, 'Formação Campestre', '#d6bc74'),
    (32, 'Apicum', '#fc8114'),
    (29, 'Afloramento Rochoso', '#ffaa5f'),
    (50, 'Restinga Herbácea', '#ad5100'),
    (15, 'Pastagem', '#edde8e'),
    (39, 'Soja', '#f5b3c8'),
    (20, 'Cana', '#db7093'),
    (40, 'Arroz', '#c71585'),
    (62, 'Algodão', '#ff69b4'),
    (41, 'Outras Lavouras Temporárias', '#f54ca9'),
    (46, 'Café', '#d68fe2'),
    (47, 'Citrus', '#9932cc'),
    (35, 'Dendê', '#9065d0'),
    (48, 'Outras Lavouras Perenes', '#e6ccff'),
    (9, 'Silvicultura', '#7a5900'),
    (21, 'Mosaico de Usos', '#ffefc3'),
    (23, 'Praia, Duna e Areal', '#ffa07a'),
    (24, 'Área Urbanizada', '#d4271e'),
    (30, 'Mineração', '#9c0027'),
    (75, 'Usina Fotovoltaica', '#c12100'),
    (25, 'Outras Áreas não Vegetadas', '#db4d4f'),
    (33, 'Rio, Lago e Oceano', '#2532e4'),
    (31, 'Aquicultura', '#091077'),
    # Classes agregadas (níveis 1 e 2), usadas onde não há detalhamento.
    (1, 'Floresta', '#1f8d49'),
    (10, 'Vegetação Herbácea e Arbustiva', '#d6bc74'),
    (14, 'Agropecuária', '#ffefc3'),
    (18, 'Agricultura', '#e974ed'),
    (19, 'Lavoura Temporária', '#c27ba0'),
    (36, 'Lavoura Perene', '#d082de'),
    (22, 'Área não Vegetada', '#d4271e'),
    (26, "Corpo D'água", '#2532e4'),
    (27, 'Não observado', '#ffffff'),
]
# Código fora da legenda (classe nova numa coleção futura): cinza.
UNKNOWN_CLASS_COLOR = '#9e9e9e'
BURNED_COLOR = '#ff3d00'

CBERS_STAC_SEARCH = 'https://data.inpe.br/bdc/stac/v1/search'
CBERS_COLLECTION = 'CB4A-WPM-PCA-FUSED-1'
# O endereço do arquivo sai do ID da cena (padrão do Brazil Data Cube); só
# IDs nesse formato são aceitos, então o servidor nunca busca URL arbitrária.
CBERS_SCENE_RE = re.compile(r'^CBERS4A_WPM_PCA_RGB321_(\d{4})(\d{2})(\d{2})_(\d{3})_(\d{3})$')
CBERS_FILE_URL = 'https://data.inpe.br/bdc/data/CB4A-WPM-PCA-FUSED/v001/{path}/{row}/{year}/{month}/{scene}.tif'
# Cena de 2 m: abaixo disso a reprojeção lê área demais (o warp do Django
# não usa a pirâmide do COG).
CBERS_MIN_ZOOM = 12
CBERS_RES = 2
CBERS_SCENES_TTL = 6 * 60 * 60
CBERS_STATS_TTL = 30 * 24 * 60 * 60

_GDAL_CONFIG = {
    'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
    'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif',
    'VSI_CACHE': 'TRUE',
    'VSI_CACHE_SIZE': str(64 * 1024 * 1024),
    'GDAL_HTTP_MULTIRANGE': 'YES',
    'GDAL_HTTP_MERGE_CONSECUTIVE_RANGES': 'YES',
    'GDAL_HTTP_TIMEOUT': '30',
    'GDAL_HTTP_MAX_RETRY': '2',
    'GDAL_CACHEMAX': '128',
}
_gdal_configured = False

# GDALRaster abertos por URL (abrir custa 1–2 s). O GDAL não aceita o mesmo
# dataset em duas threads ao mesmo tempo, daí um lock por arquivo. Cabe a
# lista de cenas CBERS de um ponto mais os anos de MapBiomas em uso.
MAX_OPEN_DATASETS = 24
_datasets = OrderedDict()
_datasets_lock = threading.Lock()


def _configure_gdal():
    global _gdal_configured
    if _gdal_configured:
        return
    lgdal.CPLSetConfigOption.argtypes = [c_char_p, c_char_p]
    for key, value in _GDAL_CONFIG.items():
        lgdal.CPLSetConfigOption(key.encode(), value.encode())
    Driver.ensure_registered()
    _gdal_configured = True


def _open(url):
    """(GDALRaster, lock) do arquivo remoto (ou local, quando `url` é um
    caminho: cenas baixadas pelo cbers2b_service), reaproveitando o já aberto.

    Abrir fica inteiro sob o lock global: duas threads abrindo arquivos (e
    registrando os drivers do GDAL) ao mesmo tempo corrompem memória e
    derrubam o processo (visto com o runserver, que atende em threads).
    """
    with _datasets_lock:
        if url in _datasets:
            _datasets.move_to_end(url)
            return _datasets[url]
        _configure_gdal()
        try:
            raster = GDALRaster('/vsicurl/' + url if url.startswith(('http://', 'https://')) else url)
        except GDALException:
            logger.warning('Não foi possível abrir o GeoTIFF %s', url)
            raise ImageryError('Arquivo de imagem indisponível.') from None
        entry = (raster, threading.Lock())
        _datasets[url] = entry
        while len(_datasets) > MAX_OPEN_DATASETS:
            _datasets.popitem(last=False)
        return entry


def _forget(url):
    with _datasets_lock:
        _datasets.pop(url, None)


@atexit.register
def _close_datasets():
    with _datasets_lock:
        _datasets.clear()


# Todo uso do GDAL roda numa única thread dedicada (daemon). Com o GDAL
# chamado de várias threads (runserver atende cada requisição numa thread),
# o processo Python não consegue encerrar no Windows, o que trava o reload
# automático do runserver. Uma thread só também dispensa locks no GDAL.
_gdal_jobs = queue.Queue()
_gdal_thread = None
_gdal_thread_lock = threading.Lock()


def _gdal_worker():
    while True:
        fn, args, done = _gdal_jobs.get()
        try:
            done['result'] = fn(*args)
        except BaseException as e:  # noqa: BLE001 - repassado a quem pediu
            done['error'] = e
        done['event'].set()


def _in_gdal_thread(fn, *args):
    global _gdal_thread
    if threading.current_thread() is _gdal_thread:
        return fn(*args)
    with _gdal_thread_lock:
        if _gdal_thread is None:
            _gdal_thread = threading.Thread(target=_gdal_worker, name='gdal-tiles', daemon=True)
            _gdal_thread.start()
    done = {'event': threading.Event()}
    _gdal_jobs.put((fn, args, done))
    done['event'].wait()
    if 'error' in done:
        raise done['error']
    return done.get('result')


def _warp_tile(url, z, x, y, resampling, buffer=0):
    return _in_gdal_thread(_warp_tile_gdal, url, z, x, y, resampling, buffer)


def _warp_tile_gdal(url, z, x, y, resampling, buffer=0):
    """Bandas (arrays numpy) do tile XYZ em EPSG:3857, lidas do GeoTIFF, com
    `buffer` pixels a mais em cada lado (margem da nitidez do realce)."""
    minx, miny, maxx, maxy = tile_bbox(z, x, y)
    pixel = (maxx - minx) / TILE_SIZE
    size = TILE_SIZE + 2 * buffer
    return _warp_window_gdal(url, (minx - buffer * pixel, maxy + buffer * pixel), pixel, size, size, resampling)


def _warp_window(url, origin, pixel, width, height, resampling):
    return _in_gdal_thread(_warp_window_gdal, url, origin, pixel, width, height, resampling)


def _warp_window_gdal(url, origin, pixel, width, height, resampling):
    """Bandas (arrays numpy) de uma janela em EPSG:3857 (`origin` = canto
    superior esquerdo, `pixel` em metros do Mercator), lidas do GeoTIFF.

    Uma leitura por HTTP que falha (conexão caída no meio) deixa o dataset
    com o bloco marcado como ruim: reabre o arquivo e tenta uma vez mais."""
    for attempt in (1, 2):
        raster, lock = _open(url)
        with lock:
            try:
                window = raster.warp({
                    'driver': 'MEM',
                    'name': 'window',
                    'srid': 3857,
                    'width': width,
                    'height': height,
                    'origin': list(origin),
                    'scale': [pixel, -pixel],
                    # Sem isso o Django copia a rotação do arquivo (o HRC do
                    # CBERS-2B corrigido tem) e o tile sai girado.
                    'skew': [0, 0],
                    'resampling': resampling,
                })
                return [band.data() for band in window.bands]
            except GDALException:
                logger.warning('Falha ao ler a janela %s (%sx%s) de %s (tentativa %s)', origin, width, height, url, attempt)
        _forget(url)
    raise ImageryError('Falha ao ler a imagem.')


def _hex_rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _palette_png(codes, palette):
    """PNG paletado: o próprio código da classe é o índice da cor. `palette`
    é {código: (r, g, b)}; códigos ausentes ficam transparentes."""
    rgb = bytearray(256 * 3)
    alpha = bytearray(256)
    for code, color in palette.items():
        rgb[code * 3:code * 3 + 3] = bytes(color)
        alpha[code] = 255
    codes = np.ascontiguousarray(codes, dtype=np.uint8)
    image = Image.frombytes('P', (codes.shape[1], codes.shape[0]), codes.tobytes())
    image.putpalette(bytes(rgb))
    out = io.BytesIO()
    image.save(out, format='PNG', transparency=bytes(alpha))
    return out.getvalue()


def _mapbiomas_palette(product, codes):
    if product == 'fogo':
        return {1: _hex_rgb(BURNED_COLOR)}
    palette = {code: _hex_rgb(color) for code, _, color in MAPBIOMAS_CLASSES}
    unknown = _hex_rgb(UNKNOWN_CLASS_COLOR)
    for code in np.unique(codes).tolist():
        if code and code not in palette:
            palette[code] = unknown
    return palette


def mapbiomas_years(product):
    first, last = MAPBIOMAS_PRODUCTS[product]['years']
    return list(range(last, first - 1, -1))


def mapbiomas_tile(product, year, z, x, y):
    """(PNG, content-type) do tile, ou None (produto/ano inválido ou zoom
    abaixo do mínimo)."""
    info = MAPBIOMAS_PRODUCTS.get(product)
    if info is None or not (info['years'][0] <= year <= info['years'][1]) or z < MAPBIOMAS_MIN_ZOOM:
        return None
    key = f'raster:mapbiomas:{product}:{year}:{z}:{x}:{y}'
    png = cache.get(key)
    if png is None:
        codes = _warp_tile(info['url'].format(year=year), z, x, y, 'NearestNeighbour')[0]
        png = _palette_png(codes, _mapbiomas_palette(product, codes))
        cache.set(key, png, TILE_TTL)
    return png, 'image/png'


def mapbiomas_legend():
    return [{'code': code, 'name': name, 'color': color} for code, name, color in MAPBIOMAS_CLASSES]


# ---------------------------------------------------------------------------
# CBERS-4A WPM (2 m) – Brazil Data Cube / INPE
# ---------------------------------------------------------------------------

def cbers_scene_url(scene):
    match = CBERS_SCENE_RE.match(scene or '')
    if not match:
        return None
    year, month, _, path, row = match.groups()
    return CBERS_FILE_URL.format(path=path, row=row, year=year, month=int(month), scene=scene)


def _scene_covers(scene, lon, lat):
    return _in_gdal_thread(_scene_covers_gdal, scene, lon, lat)


def _scene_covers_gdal(scene, lon, lat):
    """Se a cena tem imagem no ponto. O catálogo só traz o retângulo
    envolvente, e a faixa imageada é inclinada: perto da borda o retângulo
    cobre o ponto e a imagem não. Lê 1 pixel (um bloco do COG)."""
    url = cbers_scene_url(scene)
    try:
        raster, lock = _open(url)
        # Eixos na ordem lon/lat, como no WKT (o GDAL 3 usaria lat/lon no 4326).
        wgs84 = SpatialReference(4326, axis_order=AxisOrder.TRADITIONAL)
        target = SpatialReference(raster.srid, axis_order=AxisOrder.TRADITIONAL)
        point = OGRGeometry(f'POINT ({lon} {lat})', srs=wgs84)
        point.transform(CoordTransform(wgs84, target))
        col = int((point.x - raster.origin.x) / raster.scale.x)
        row = int((point.y - raster.origin.y) / raster.scale.y)
        if not (0 <= col < raster.width and 0 <= row < raster.height):
            return False
        with lock:
            return any(int(raster.bands[i].data(offset=(col, row), size=(1, 1))[0][0]) for i in range(3))
    except (ImageryError, GDALException):
        return False


def cbers_scenes(lon, lat):
    """Cenas CBERS-4A WPM com imagem no ponto, da mais recente à mais
    antiga."""
    key = f'raster:cbers:scenes:{round(lon, 2)}:{round(lat, 2)}'
    scenes = cache.get(key)
    if scenes is not None:
        return scenes
    try:
        response = requests.post(CBERS_STAC_SEARCH, json={
            'collections': [CBERS_COLLECTION],
            'intersects': {'type': 'Point', 'coordinates': [lon, lat]},
            'limit': 100,
        }, timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning('Falha de conexão com o catálogo do INPE: %s', type(e).__name__)
        raise ImageryError('Catálogo do INPE indisponível.') from None
    if response.status_code != 200:
        raise ImageryError(f'Catálogo do INPE respondeu com erro {response.status_code}.')
    candidates = []
    for feature in response.json().get('features', []):
        if cbers_scene_url(feature.get('id')):
            candidates.append({'id': feature['id'], 'date': (feature.get('properties', {}).get('datetime') or '')[:10]})
    candidates.sort(key=lambda s: s['date'], reverse=True)
    scenes = [s for s in candidates if _scene_covers(s['id'], lon, lat)]
    cache.set(key, scenes, CBERS_SCENES_TTL)
    return scenes


def _band_stats(url):
    raster, lock = _open(url)
    with lock:
        try:
            return [raster.bands[i].statistics(approximate=True) for i in range(3)]
        except GDALException:
            raise ImageryError('Falha ao ler a imagem.') from None


def _cbers_stretch(scene, url):
    """Faixa de contraste por banda (média −2σ a +3σ da cena inteira, pela
    pirâmide do COG): corrige o tom arroxeado da fusão sem emendas entre
    tiles, que teriam contraste diferente se fosse calculado por tile."""
    key = f'raster:cbers:stretch:{scene}'
    stretch = cache.get(key)
    if stretch is not None:
        return stretch
    stats = _in_gdal_thread(_band_stats, url)
    stretch = [(max(1.0, s[2] - 2 * s[3]), s[2] + 3 * s[3]) for s in stats]
    cache.set(key, stretch, CBERS_STATS_TTL)
    return stretch


def stretch_band(band, lo, hi):
    """Banda esticada de `lo`–`hi` para 0–255 (uint8)."""
    return np.clip((band.astype(np.float32) - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)


def enhanced_read(url, z, x, y, source_res):
    """(bandas com margem, raio, margem) para um tile realçado: interpolação
    bicúbica e a margem que a nitidez de `image_enhance` precisa."""
    radius = image_enhance.sharpen_radius(source_res, z, y)
    buffer = image_enhance.sharpen_buffer(radius)
    return _warp_tile(url, z, x, y, 'Cubic', buffer), radius, buffer


def rgba_webp(rgba, radius=0, buffer=0):
    """WEBP do RGBA (h×w×4); com `radius`, aplica a nitidez do realce e corta
    a margem."""
    if radius:
        rgba = image_enhance.sharpen_rgba(rgba, radius, buffer)
    rgba = np.ascontiguousarray(rgba)
    out = io.BytesIO()
    Image.frombytes('RGBA', (rgba.shape[1], rgba.shape[0]), rgba.tobytes()).save(out, format='WEBP', quality=82)
    return out.getvalue()


def cbers_tile(scene, z, x, y, enhance=False):
    """(WEBP com transparência, content-type), ou None fora do zoom/cena.
    `enhance`: interpolação bicúbica e nitidez na escala do pixel de 2 m."""
    url = cbers_scene_url(scene)
    if url is None or z < CBERS_MIN_ZOOM:
        return None
    key = f'raster:cbers:{scene}:{"realce" if enhance else "padrao"}:{z}:{x}:{y}'
    webp = cache.get(key)
    if webp is None:
        if enhance:
            bands, radius, buffer = enhanced_read(url, z, x, y, CBERS_RES)
        else:
            bands, radius, buffer = _warp_tile(url, z, x, y, 'Bilinear'), 0, 0
        bands = bands[:3]
        stretch = _cbers_stretch(scene, url)
        rgb = np.dstack([stretch_band(band, lo, hi) for band, (lo, hi) in zip(bands, stretch)])
        # 0 nas três bandas = fora da faixa imageada.
        alpha = np.where((bands[0] == 0) & (bands[1] == 0) & (bands[2] == 0), 0, 255).astype(np.uint8)
        webp = rgba_webp(np.dstack([rgb, alpha]), radius, buffer)
        cache.set(key, webp, TILE_TTL)
    return webp, 'image/webp'
