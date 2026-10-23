"""Imagens de satélite do mapa de resultados: provedores OGC configurados
por link (Planet, Copernicus), Google e Esri Wayback.

As chaves ficam só no servidor: o navegador pede os tiles às views de
`analysis/urls.py`, que repassam a requisição ao provedor. A Esri Wayback é
pública, então o navegador busca os tiles direto na Esri.
"""
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from analysis.services.view_services import image_enhance

logger = logging.getLogger(__name__)

TIMEOUT = 20
# GetCapabilities de contas com muitos mosaicos chega a vários MB.
CAPABILITIES_TIMEOUT = 60
TILE_SIZE = 256
WEB_MERCATOR_HALF = math.pi * 6378137

WAYBACK_CONFIG_URL = 'https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json'
WAYBACK_TILE_URL = (
    'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/'
    'default028mm/MapServer/tile/{release}/{z}/{y}/{x}'
)
PLANET_WMTS_URL = 'https://api.planet.com/basemaps/v1/mosaics/wmts'
GOOGLE_TILES_URL = 'https://tile.googleapis.com/v1'

CAPABILITIES_CACHE_KEY = 'imagery:{provider}:capabilities'
CAPABILITIES_TTL = 60 * 60
# v2: entradas passaram a ter metadata_url (a v1 em cache não tem).
WAYBACK_CACHE_KEY = 'imagery:wayback:releases:v2'
WAYBACK_TTL = 24 * 60 * 60
GOOGLE_SESSION_CACHE_KEY = 'imagery:google:session'

# Parâmetros que este módulo define em toda requisição WMS/WMTS; se vierem no
# link configurado (ex.: o link copiado do QGIS traz REQUEST=GetCapabilities),
# são descartados para não conflitar.
OGC_PARAMS = {
    'service', 'request', 'version', 'layers', 'layer', 'styles', 'style', 'format',
    'crs', 'srs', 'bbox', 'width', 'height', 'transparent', 'tilematrixset',
    'tilematrix', 'tilerow', 'tilecol',
}
WEB_MERCATOR_CODES = ('3857', '900913', '102100', '3785')

_http = requests.Session()


class ImageryError(Exception):
    """Falha ao falar com o provedor de imagens (sem expor URL nem chave)."""


# ---------------------------------------------------------------------------
# Configuração para o maps.js
# ---------------------------------------------------------------------------

# Provedores com link OGC (WMS ou WMTS) e a chave no próprio link. `name`
# vai nas mensagens de erro; o resto é o que o seletor do maps.js mostra.
OGC_PROVIDERS = {
    'planet': {
        'name': 'Planet',
        'base_name': 'Satélite (Planet)',
        'label': 'Mosaico Planet',
        'attribution': 'Imagens &copy; Planet Labs PBC',
    },
    'copernicus': {
        'name': 'Copernicus',
        'base_name': 'Copernicus (Sentinel)',
        'label': 'Camada Copernicus',
        'attribution': 'Contém dados Copernicus Sentinel modificados',
        # O WMS do Copernicus Data Space não informa resolução; depende do
        # satélite da camada configurada lá.
        'resolution_hint': 'Resolução: 10 m (Sentinel-1 e Sentinel-2)',
    },
}


def provider_source_url(provider):
    """Link OGC configurado do provedor, ou '' quando não está configurado.
    Planet sem `PLANET_WMS_URL` usa o WMTS de basemaps de `PLANET_API_KEY`."""
    if provider == 'planet':
        url = getattr(settings, 'PLANET_WMS_URL', '')
        if url:
            return url
        key = getattr(settings, 'PLANET_API_KEY', '')
        return f'{PLANET_WMTS_URL}?api_key={key}' if key else ''
    if provider == 'copernicus':
        return getattr(settings, 'COPERNICUS_WMS_URL', '')
    return ''


def imagery_config():
    """Fontes de imagem que o maps.js oferece no seletor de mapa base. Os
    provedores OGC e o Google só entram quando a chave está configurada."""
    # Os placeholders do Leaflet ({layer}/{z}/{x}/{y}) não passam pelo
    # `reverse`, então trocamos um tile fictício por eles.
    config = {
        'wayback_tile_url': WAYBACK_TILE_URL,
        'wayback_releases_url': reverse('imagery_wayback_releases'),
        'providers': [],
    }
    for provider, meta in OGC_PROVIDERS.items():
        if not provider_source_url(provider):
            continue
        config['providers'].append({
            'key': provider,
            **{k: v for k, v in meta.items() if k != 'name'},
            'layers_url': reverse('imagery_provider_layers', args=(provider,)),
            'tile_url': reverse('imagery_provider_tile', args=(provider, 'LAYER', 0, 0, 0)).replace(
                '/LAYER/0/0/0', '/{layer}/{z}/{x}/{y}'),
        })
    if getattr(settings, 'GOOGLE_MAPS_API_KEY', ''):
        config['google_tile_url'] = reverse('imagery_google_tile', args=(0, 0, 0)).replace(
            '/0/0/0', '/{z}/{x}/{y}')

    # Tiles gerados no servidor (raster_tiles importa este módulo).
    from analysis.services.view_services import raster_tiles
    config['mapbiomas'] = {
        'tile_url': reverse('imagery_mapbiomas_tile', args=('PRODUTO', 2000, 0, 0, 0)).replace(
            '/PRODUTO/2000/0/0/0.png', '/{product}/{year}/{z}/{x}/{y}.png'),
        'min_zoom': raster_tiles.MAPBIOMAS_MIN_ZOOM,
        'legend': raster_tiles.mapbiomas_legend(),
        'burned_color': raster_tiles.BURNED_COLOR,
        'products': {
            product: {'name': info['name'], 'years': raster_tiles.mapbiomas_years(product)}
            for product, info in raster_tiles.MAPBIOMAS_PRODUCTS.items()
        },
    }
    config['cbers'] = {
        'scenes_url': reverse('imagery_cbers_scenes'),
        'tile_url': reverse('imagery_cbers_tile', args=('CENA', 0, 0, 0)).replace(
            '/CENA/0/0/0.webp', '/{scene}/{z}/{x}/{y}.webp'),
        'min_zoom': raster_tiles.CBERS_MIN_ZOOM,
    }
    config['landsat_legacy'] = {
        'scenes_url': reverse('imagery_landsat_legacy_scenes'),
        'tile_url': reverse('imagery_landsat_legacy_tile', args=('CENA', 'COMP', 0, 0, 0)).replace(
            '/CENA/COMP/0/0/0.png', '/{scene}/{comp}/{z}/{x}/{y}.png'),
        'max_native_zoom': LANDSAT_LEGACY_MAX_NATIVE_ZOOM,
        'enhanced_max_zoom': LANDSAT_LEGACY_ENHANCED_MAX_ZOOM,
        'years': list(LANDSAT_LEGACY_YEARS),
        'compositions': [{'value': k, 'text': v['label']} for k, v in LANDSAT_LEGACY_COMPOSITIONS.items()],
    }
    from analysis.services.view_services import cbers2b_service
    config['cbers2b'] = {
        'scenes_url': reverse('imagery_cbers2b_scenes'),
        'prepare_url': reverse('imagery_cbers2b_prepare', args=('CENA',)).replace('CENA', '{scene}'),
        'progress_url': reverse('imagery_cbers2b_progress', args=('CENA',)).replace('CENA', '{scene}'),
        'tile_url': reverse('imagery_cbers2b_tile', args=('CENA', 'COMP', 0, 0, 0)).replace(
            '/CENA/COMP/0/0/0.webp', '/{scene}/{comp}/{z}/{x}/{y}.webp'),
        'min_zoom': cbers2b_service.HRC_MIN_ZOOM,
        'years': list(cbers2b_service.HRC_YEARS),
    }
    return config


# ---------------------------------------------------------------------------
# Provedores OGC (WMS ou WMTS)
# ---------------------------------------------------------------------------

def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _child(el, name):
    found = _children(el, name)
    return found[0] if found else None


def _text(el, name):
    c = _child(el, name)
    return (c.text or '').strip() if c is not None and c.text else ''


def _split_url(url):
    """Separa o link em (url sem query, parâmetros extras como a chave,
    serviço indicado no link: 'WMS', 'WMTS' ou '')."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    extra = [(k, v) for k, v in query if k.lower() not in OGC_PARAMS]
    service = next((v.upper() for k, v in query if k.lower() == 'service'), '')
    return urlunsplit(parts._replace(query='')), extra, service


def _capabilities_params(base_url, extra, service):
    """Parâmetros do GetCapabilities. Links WMTS no estilo REST (como o de
    basemaps da Planet) não levam SERVICE/REQUEST; os KVP levam."""
    if service == 'WMTS':
        return extra + [('SERVICE', 'WMTS'), ('REQUEST', 'GetCapabilities')]
    if service == 'WMS' or 'wmts' not in base_url.lower():
        return extra + [('SERVICE', 'WMS'), ('REQUEST', 'GetCapabilities')]
    return extra


def _get(url, params=None, timeout=TIMEOUT):
    try:
        response = _http.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        # A mensagem do requests traz a URL, que tem a chave: não repassar.
        logger.warning('Falha de conexão com o provedor de imagens: %s', type(e).__name__)
        raise ImageryError('Provedor de imagens indisponível.') from None
    return response


def parse_capabilities(xml_bytes, base_url, extra_params):
    """Lê o GetCapabilities (WMS 1.1.1/1.3.0 ou WMTS 1.0.0) e devolve as
    camadas que podem ser desenhadas em Web Mercator."""
    root = ET.fromstring(xml_bytes)
    name = _local(root.tag)
    if name in ('WMS_Capabilities', 'WMT_MS_Capabilities'):
        return _parse_wms(root, base_url, extra_params)
    if name == 'Capabilities':
        return _parse_wmts(root, base_url, extra_params)
    raise ImageryError('O link configurado não é um serviço WMS ou WMTS.')


def _parse_wms(root, base_url, extra_params):
    version = root.get('version') or '1.3.0'
    formats = []
    capability = _child(root, 'Capability')
    request_el = _child(capability, 'Request') if capability is not None else None
    getmap = _child(request_el, 'GetMap') if request_el is not None else None
    if getmap is not None:
        formats = [(f.text or '').strip() for f in _children(getmap, 'Format')]
    image_format = next((f for f in ('image/png', 'image/jpeg') if f in formats), 'image/png')

    layers = {}
    if capability is not None:
        for layer_el in capability.iter():
            if _local(layer_el.tag) != 'Layer':
                continue
            layer_id = _text(layer_el, 'Name')
            if not layer_id:
                continue  # camada-grupo, sem nome próprio
            layers[layer_id] = {'title': _text(layer_el, 'Title') or layer_id}

    return {
        'kind': 'wms',
        'base_url': base_url,
        'extra_params': extra_params,
        'version': version,
        'format': image_format,
        'layers': layers,
    }


def _matrix_sets(root):
    """{id do TileMatrixSet: [ids de TileMatrix por zoom]} só dos que estão
    em Web Mercator."""
    contents = _child(root, 'Contents')
    sets = {}
    if contents is None:
        return sets
    for tms in _children(contents, 'TileMatrixSet'):
        crs = _text(tms, 'SupportedCRS')
        if not any(code in crs for code in WEB_MERCATOR_CODES):
            continue
        matrices = [_text(tm, 'Identifier') for tm in _children(tms, 'TileMatrix')]
        sets[_text(tms, 'Identifier')] = matrices
    return sets


def _parse_wmts(root, base_url, extra_params):
    sets = _matrix_sets(root)
    contents = _child(root, 'Contents')
    layers = {}
    for layer_el in (_children(contents, 'Layer') if contents is not None else []):
        layer_id = _text(layer_el, 'Identifier')
        links = [_text(link, 'TileMatrixSet') for link in _children(layer_el, 'TileMatrixSetLink')]
        matrix_set = next((s for s in links if s in sets), None)
        if not layer_id or not matrix_set:
            continue
        template = ''
        for resource in _children(layer_el, 'ResourceURL'):
            if resource.get('resourceType') == 'tile':
                template = resource.get('template') or ''
                break
        formats = [(f.text or '').strip() for f in _children(layer_el, 'Format')]
        style_el = next((s for s in _children(layer_el, 'Style') if s.get('isDefault') == 'true'),
                        _child(layer_el, 'Style'))
        layers[layer_id] = {
            'title': _text(layer_el, 'Title') or layer_id,
            'template': template,
            'matrix_set': matrix_set,
            'matrices': sets[matrix_set],
            'format': next((f for f in ('image/png', 'image/jpeg') if f in formats), formats[0] if formats else 'image/png'),
            'style': _text(style_el, 'Identifier') if style_el is not None else 'default',
        }
    return {
        'kind': 'wmts',
        'base_url': base_url,
        'extra_params': extra_params,
        'layers': layers,
    }


def provider_capabilities(provider):
    cache_key = CAPABILITIES_CACHE_KEY.format(provider=provider)
    capabilities = cache.get(cache_key)
    if capabilities:
        return capabilities

    source = provider_source_url(provider)
    if not source:
        raise ImageryError('Provedor de imagens não configurado.')
    name = OGC_PROVIDERS[provider]['name']
    base_url, extra, service = _split_url(source)
    response = _get(base_url, _capabilities_params(base_url, extra, service), CAPABILITIES_TIMEOUT)
    if response.status_code in (401, 403):
        raise ImageryError(f'{name} recusou a chave configurada.')
    if response.status_code != 200:
        raise ImageryError(f'{name} respondeu com erro {response.status_code}.')
    try:
        capabilities = parse_capabilities(response.content, base_url, extra)
    except ET.ParseError:
        raise ImageryError(f'Resposta inválida de {name}.') from None
    cache.set(cache_key, capabilities, CAPABILITIES_TTL)
    return capabilities


def provider_layers(provider):
    """Lista de camadas/mosaicos do provedor para o seletor do mapa."""
    capabilities = provider_capabilities(provider)
    layers = []
    for layer_id, info in capabilities['layers'].items():
        layer = {'id': layer_id, 'title': info['title']}
        if info.get('matrices'):
            # Último zoom com imagem; acima disso o mapa amplia esse nível.
            layer['max_zoom'] = len(info['matrices']) - 1
        layers.append(layer)
    return layers


def tile_bbox(z, x, y):
    """BBOX em EPSG:3857 do tile XYZ."""
    size = 2 * WEB_MERCATOR_HALF / (2 ** z)
    minx = -WEB_MERCATOR_HALF + x * size
    maxy = WEB_MERCATOR_HALF - y * size
    return minx, maxy - size, minx + size, maxy


def _wms_tile_request(capabilities, layer_id, z, x, y):
    version = capabilities['version']
    bbox = ','.join(f'{v:.6f}' for v in tile_bbox(z, x, y))
    params = list(capabilities['extra_params']) + [
        ('SERVICE', 'WMS'),
        ('REQUEST', 'GetMap'),
        ('VERSION', version),
        ('LAYERS', layer_id),
        ('STYLES', ''),
        ('FORMAT', capabilities['format']),
        ('TRANSPARENT', 'true' if capabilities['format'] == 'image/png' else 'false'),
        ('CRS' if version.startswith('1.3') else 'SRS', 'EPSG:3857'),
        ('BBOX', bbox),
        ('WIDTH', str(TILE_SIZE)),
        ('HEIGHT', str(TILE_SIZE)),
    ]
    return capabilities['base_url'], params


def _wmts_tile_request(capabilities, layer, layer_id, z, x, y):
    matrices = layer['matrices']
    if z >= len(matrices):
        return None, None
    matrix = matrices[z]
    if layer['template']:
        url = (layer['template']
               .replace('{TileMatrixSet}', layer['matrix_set'])
               .replace('{TileMatrix}', matrix)
               .replace('{TileRow}', str(y))
               .replace('{TileCol}', str(x))
               .replace('{Style}', layer['style']))
        return url, None
    params = list(capabilities['extra_params']) + [
        ('SERVICE', 'WMTS'),
        ('REQUEST', 'GetTile'),
        ('VERSION', '1.0.0'),
        ('LAYER', layer_id),
        ('STYLE', layer['style']),
        ('FORMAT', layer['format']),
        ('TILEMATRIXSET', layer['matrix_set']),
        ('TILEMATRIX', matrix),
        ('TILEROW', str(y)),
        ('TILECOL', str(x)),
    ]
    return capabilities['base_url'], params


def provider_tile(provider, layer_id, z, x, y):
    """(bytes, content-type) do tile, ou None quando não há imagem ali."""
    capabilities = provider_capabilities(provider)
    layer = capabilities['layers'].get(layer_id)
    if layer is None:
        return None
    if capabilities['kind'] == 'wms':
        url, params = _wms_tile_request(capabilities, layer_id, z, x, y)
    else:
        url, params = _wmts_tile_request(capabilities, layer, layer_id, z, x, y)
        if url is None:
            return None
    return _image_response(_get(url, params), OGC_PROVIDERS[provider]['name'])


def _image_response(response, provider):
    if response.status_code in (204, 404):
        return None
    content_type = response.headers.get('Content-Type', '')
    if response.status_code != 200 or not content_type.startswith('image/'):
        # WMS devolve erro como XML com status 200; não repassar como imagem.
        logger.warning('%s devolveu status %s (%s) para um tile.', provider, response.status_code, content_type)
        raise ImageryError(f'{provider} não devolveu imagem.')
    return response.content, content_type


# ---------------------------------------------------------------------------
# Google (Map Tiles API, imagem de satélite)
# ---------------------------------------------------------------------------

def _google_session(force_new=False):
    session = None if force_new else cache.get(GOOGLE_SESSION_CACHE_KEY)
    if session:
        return session
    key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    if not key:
        raise ImageryError('Google não configurado.')
    try:
        response = _http.post(
            f'{GOOGLE_TILES_URL}/createSession',
            params={'key': key},
            json={'mapType': 'satellite', 'language': 'pt-BR', 'region': 'BR'},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning('Falha de conexão com o Google Map Tiles: %s', type(e).__name__)
        raise ImageryError('Google indisponível.') from None
    if response.status_code != 200:
        logger.warning('Google Map Tiles recusou a criação de sessão (status %s).', response.status_code)
        raise ImageryError('O Google recusou a chave configurada.')
    data = response.json()
    session = data['session']
    # A sessão vale ~2 semanas; renova uma hora antes de expirar.
    ttl = int(float(data.get('expiry', 0)) - time.time()) - 3600
    cache.set(GOOGLE_SESSION_CACHE_KEY, session, max(ttl, 60))
    return session


def google_tile(z, x, y):
    key = getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    url = f'{GOOGLE_TILES_URL}/2dtiles/{z}/{x}/{y}'
    response = _get(url, {'session': _google_session(), 'key': key})
    if response.status_code in (400, 401, 403):
        # Sessão expirada ou invalidada antes do previsto: cria outra e tenta de novo.
        response = _get(url, {'session': _google_session(force_new=True), 'key': key})
    return _image_response(response, 'Google')


# ---------------------------------------------------------------------------
# Esri Wayback (histórico da imagem World Imagery)
# ---------------------------------------------------------------------------

def wayback_releases():
    """Versões da imagem da Esri, da mais recente para a mais antiga."""
    releases = cache.get(WAYBACK_CACHE_KEY)
    if releases:
        return releases
    response = _get(WAYBACK_CONFIG_URL)
    if response.status_code != 200:
        raise ImageryError('Esri Wayback indisponível.')
    releases = []
    for release_id, info in response.json().items():
        match = re.search(r'(\d{4}-\d{2}-\d{2})', info.get('itemTitle', ''))
        if match:
            releases.append({
                'id': int(release_id),
                'date': match.group(1),
                # Serviço com sensor, data de captura e resolução por região
                # daquela versão (consultado direto pelo maps.js).
                'metadata_url': info.get('metadataLayerUrl', ''),
            })
    releases.sort(key=lambda r: r['date'], reverse=True)
    cache.set(WAYBACK_CACHE_KEY, releases, WAYBACK_TTL)
    return releases


# ---------------------------------------------------------------------------
# Landsat 4/5/7 (1984–2012) – Microsoft Planetary Computer
# ---------------------------------------------------------------------------
# Acervo Landsat Collection 2 nível 2 (reflectância de superfície), público e
# sem chave. O serviço Landsat da Esri (já no mapa) só tem as épocas GLS
# antes de 2013; daqui vêm as cenas anuais, ex.: 2008 (marco do Código Florestal).

PC_STAC_SEARCH = 'https://planetarycomputer.microsoft.com/api/stac/v1/search'
PC_TILE_URL = 'https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x.png'
PC_STATS_URL = 'https://planetarycomputer.microsoft.com/api/data/v1/item/statistics'
PC_BBOX_URL = 'https://planetarycomputer.microsoft.com/api/data/v1/item/bbox/{minx},{miny},{maxx},{maxy}/{width}x{height}.tif'
LANDSAT_LEGACY_COLLECTION = 'landsat-c2-l2'
LANDSAT_LEGACY_YEARS = (1984, 2012)
LANDSAT_LEGACY_PLATFORMS = ['landsat-4', 'landsat-5', 'landsat-7']
LANDSAT_LEGACY_MAX_CLOUD = 40
# Cenas por ano no seletor (as de menos nuvem).
LANDSAT_LEGACY_PER_YEAR = 5
# O Landsat 7 tem faixas sem dado desde 31/05/2003 (falha do SLC): perde
# para uma cena do Landsat 5 com até esse tanto a mais de nuvem.
LANDSAT7_SLC_OFF_YEAR = 2003
LANDSAT7_SLC_OFF_PENALTY = 15
LANDSAT_LEGACY_SCENES_TTL = 24 * 60 * 60
LANDSAT_LEGACY_TILE_TTL = 7 * 24 * 60 * 60
LANDSAT_LEGACY_MAX_NATIVE_ZOOM = 15
LANDSAT_LEGACY_RES = 30
# "Melhorar imagem": o servidor de tiles reamostra com interpolação bicúbica
# até esse zoom (1 px ≈ 1 m), em vez de o navegador ampliar o pixel de 30 m.
LANDSAT_LEGACY_ENHANCED_MAX_ZOOM = 17
LANDSAT_LEGACY_RESAMPLING = 'cubic'
# Clareia os tons médios que o piso mais alto escurece (rio-color).
LANDSAT_LEGACY_COLOR_FORMULA = 'Gamma RGB 1.25'
LANDSAT_LEGACY_STATS_TTL = 30 * 24 * 60 * 60
# Sem estatística (servidor fora do ar), tenta de novo depois disso.
LANDSAT_LEGACY_STATS_RETRY_TTL = 10 * 60
# Faixa mínima do contraste (DN; ≈ 4 % de reflectância): numa cena muito
# uniforme, esticar menos que isso só realça ruído.
LANDSAT_LEGACY_MIN_SPAN = 1500
LANDSAT_SCENE_RE = re.compile(r'^L[TE]0[457]_L2SP_\d{6}_(\d{8})_\d{2}_T[12]$')

# Bandas e contraste (valores digitais da Collection 2: refl = DN·0,0000275 − 0,2).
LANDSAT_LEGACY_COMPOSITIONS = {
    'natural': {'label': 'Cor natural', 'assets': ['red', 'green', 'blue'], 'rescale': '7500,13500'},
    'falsa_cor': {'label': 'Falsa cor (vegetação em vermelho)', 'assets': ['nir08', 'red', 'green'], 'rescale': '7500,22000'},
    'infravermelho': {'label': 'Infravermelho (SWIR – solo exposto e desmate)', 'assets': ['swir16', 'nir08', 'red'], 'rescale': '7500,24000'},
}


def _landsat_legacy_rank(scene):
    penalty = LANDSAT7_SLC_OFF_PENALTY if scene['platform'] == 'landsat-7' and int(scene['date'][:4]) >= LANDSAT7_SLC_OFF_YEAR else 0
    return scene['cloud'] + penalty


def landsat_legacy_scenes(lon, lat):
    """Cenas Landsat 4/5/7 de 1984 a 2012 sobre o ponto: as de menos nuvem de
    cada ano, do ano mais recente ao mais antigo."""
    key = f'imagery:landsat-legacy:scenes:{round(lon, 2)}:{round(lat, 2)}'
    scenes = cache.get(key)
    if scenes is not None:
        return scenes
    first, last = LANDSAT_LEGACY_YEARS
    body = {
        'collections': [LANDSAT_LEGACY_COLLECTION],
        'intersects': {'type': 'Point', 'coordinates': [lon, lat]},
        'datetime': f'{first}-01-01T00:00:00Z/{last}-12-31T23:59:59Z',
        'query': {'platform': {'in': LANDSAT_LEGACY_PLATFORMS}, 'eo:cloud_cover': {'lt': LANDSAT_LEGACY_MAX_CLOUD}},
        'fields': {'include': ['id', 'properties.datetime', 'properties.platform', 'properties.eo:cloud_cover']},
        'limit': 1000,
    }
    features = []
    # Paginação pelo link "next" (POST com o corpo que ele traz).
    for _ in range(5):
        try:
            response = _http.post(PC_STAC_SEARCH, json=body, timeout=TIMEOUT)
        except requests.RequestException as e:
            logger.warning('Falha de conexão com o catálogo do Planetary Computer: %s', type(e).__name__)
            raise ImageryError('Catálogo do Landsat indisponível.') from None
        if response.status_code != 200:
            raise ImageryError(f'Catálogo do Landsat respondeu com erro {response.status_code}.')
        page = response.json()
        features.extend(page.get('features', []))
        nxt = next((link for link in page.get('links', []) if link.get('rel') == 'next'), None)
        if not nxt or not nxt.get('body'):
            break
        body = nxt['body']

    by_year = {}
    for feature in features:
        props = feature.get('properties', {})
        if not LANDSAT_SCENE_RE.match(feature.get('id', '')):
            continue
        scene = {
            'id': feature['id'],
            'date': (props.get('datetime') or '')[:10],
            'platform': props.get('platform', ''),
            'cloud': round(props.get('eo:cloud_cover') or 0),
        }
        by_year.setdefault(scene['date'][:4], []).append(scene)
    scenes = []
    for year in sorted(by_year, reverse=True):
        best = sorted(by_year[year], key=_landsat_legacy_rank)[:LANDSAT_LEGACY_PER_YEAR]
        scenes.extend(sorted(best, key=lambda s: s['date'], reverse=True))
    cache.set(key, scenes, LANDSAT_LEGACY_SCENES_TTL)
    return scenes


def landsat_legacy_stretch(scene, composition):
    """Contraste por banda da cena para o realce.

    O piso sobe até o menor percentil 2 entre as bandas: tira o véu da
    atmosfera sem mudar a cor (um piso por banda deixava a vegetação marrom).
    O teto fica o da composição: com o percentil 98 de uma cena quase toda de
    vegetação, cidade e solo exposto estouravam em branco. Sai da cena
    inteira (não do tile), então os tiles não têm emenda entre si."""
    comp = LANDSAT_LEGACY_COMPOSITIONS[composition]
    key = f'imagery:landsat-legacy:stretch:{scene}:{composition}'
    stretch = cache.get(key)
    if stretch is not None:
        return stretch
    base_lo, base_hi = (float(v) for v in comp['rescale'].split(','))
    params = [('collection', LANDSAT_LEGACY_COLLECTION), ('item', scene), ('nodata', '0'),
              ('max_size', '512'), ('p', '2')]
    params += [('assets', asset) for asset in comp['assets']]
    stats = {}
    try:
        response = _get(PC_STATS_URL, params, timeout=CAPABILITIES_TIMEOUT)
        if response.status_code == 200:
            stats = response.json()
    except (ImageryError, ValueError):
        pass
    if not stats:
        logger.warning('Sem estatística da cena %s: realce com o contraste padrão.', scene)
    floors = [(stats.get(f'{asset}_b1') or {}).get('percentile_2', base_lo) for asset in comp['assets']]
    lo = min(max(base_lo, min(floors)), base_hi - LANDSAT_LEGACY_MIN_SPAN)
    stretch = (round(lo), round(base_hi))
    cache.set(key, stretch, LANDSAT_LEGACY_STATS_TTL if stats else LANDSAT_LEGACY_STATS_RETRY_TTL)
    return stretch


def landsat_legacy_tile(scene, composition, z, x, y, enhance=False):
    """(PNG com transparência, content-type), ou None fora da cena.

    `enhance` ("Melhorar imagem"): contraste da própria cena, interpolação
    bicúbica até o zoom 17 e nitidez na escala do pixel de 30 m."""
    comp = LANDSAT_LEGACY_COMPOSITIONS.get(composition)
    max_zoom = LANDSAT_LEGACY_ENHANCED_MAX_ZOOM if enhance else LANDSAT_LEGACY_MAX_NATIVE_ZOOM
    if comp is None or not LANDSAT_SCENE_RE.match(scene or '') or z > max_zoom:
        return None
    key = f'imagery:landsat-legacy:{scene}:{composition}:{"realce" if enhance else "padrao"}:{z}:{x}:{y}'
    tile = cache.get(key)
    if tile is not None:
        return tile
    params = [('collection', LANDSAT_LEGACY_COLLECTION), ('item', scene), ('nodata', '0')]
    params += [('assets', asset) for asset in comp['assets']]
    if not enhance:
        params.append(('rescale', comp['rescale']))
        tile = _image_response(_get(PC_TILE_URL.format(z=z, x=x, y=y), params), 'Planetary Computer')
    else:
        lo, hi = landsat_legacy_stretch(scene, composition)
        params += [('rescale', f'{lo},{hi}'), ('color_formula', LANDSAT_LEGACY_COLOR_FORMULA)]
        radius = image_enhance.sharpen_radius(LANDSAT_LEGACY_RES, z, y)
        buffer = image_enhance.sharpen_buffer(radius)
        # `reproject` é a reamostragem do warp para o Web Mercator (é ela que
        # amplia o pixel); `resampling` só vale para ler a pirâmide do COG.
        params += [('reproject', LANDSAT_LEGACY_RESAMPLING), ('buffer', str(buffer))]
        tile = _image_response(_get(PC_TILE_URL.format(z=z, x=x, y=y), params), 'Planetary Computer')
        if tile is not None:
            tile = image_enhance.sharpen_png(tile[0], radius, buffer), 'image/png'
    cache.set(key, tile, LANDSAT_LEGACY_TILE_TTL)
    return tile
