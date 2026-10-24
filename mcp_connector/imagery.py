"""Fundos do mapa do conector e a fonte de cada imagem.

Toda imagem que o conector entrega diz de onde ela veio (`fonte_imagem`):
satélite e sensor, data da captura, resolução e provedor. As mesmas
informações saem impressas no rodapé da legenda do PNG.

- Satélite atual: Esri World Imagery na versão mais recente da Esri Wayback,
  cujos metadados dizem, para a área, o satélite e a data de cada captura.
- Imagem de um ano: 1984–2012, Landsat 4/5/7 (USGS/NASA, pelo Planetary
  Computer, o mesmo acervo do mapa de resultados); de 2014 em diante, a versão
  da Esri Wayback daquele ano.
- Uso do solo: MapBiomas (cobertura e uso da terra), com a parte de cada
  classe dentro do imóvel.
"""
import io
import math
from datetime import date, datetime, timezone

import numpy as np
import requests
from PIL import Image, ImageDraw

from analysis.services.view_services import imagery_service, raster_tiles
from analysis.services.view_services.imagery_service import (
    LANDSAT_LEGACY_COMPOSITIONS,
    LANDSAT_LEGACY_ENHANCED_MAX_ZOOM,
    LANDSAT_LEGACY_YEARS,
    LANDSAT7_SLC_OFF_YEAR,
    WAYBACK_TILE_URL,
    ImageryError,
)

from . import static_map
from .static_map import Basemap, MapRenderError

TIMEOUT = 15
EARTH_HALF = math.pi * 6378137
ESRI_FIELDS = 'SRC_DATE2,SRC_RES,SRC_ACC,SRC_DESC,NICE_DESC'
# Capturas listadas por imagem (o mosaico da Esri pode juntar várias na mesma área).
MAX_CAPTURES = 4
# Primeiro ano com versão na Esri Wayback (a mais antiga é de 20/02/2014).
WAYBACK_FIRST_YEAR = 2014
# Marco temporal do Código Florestal (22/07/2008): entre cenas com a mesma
# nuvem, fica a mais perto dessa época do ano (seca no Cerrado).
REFERENCE_DAY_OF_YEAR = 204
# Classes com menos que isso do imóvel não entram na legenda.
MIN_CLASS_PCT = 0.5
MAX_CLASSES_IN_LEGEND = 9

SENSORS = {
    'WV01': 'WorldView-1', 'WV02': 'WorldView-2', 'WV03': 'WorldView-3', 'WV04': 'WorldView-4',
    'GE01': 'GeoEye-1', 'QB02': 'QuickBird-2', 'IK01': 'IKONOS', 'IK02': 'IKONOS',
}
LANDSAT_PLATFORMS = {
    'landsat-4': ('Landsat 4', 'TM'),
    'landsat-5': ('Landsat 5', 'TM'),
    'landsat-7': ('Landsat 7', 'ETM+'),
}
LANDSAT_PROVIDER = 'USGS/NASA (Landsat Collection 2, nível 2), via Microsoft Planetary Computer'
MAPBIOMAS_PRODUCT = 'cobertura'


def _br_date(value):
    return f'{value[8:10]}/{value[5:7]}/{value[:4]}' if value and len(value) >= 10 else value


def _meters(value):
    if value is None:
        return ''
    text = f'{value:.2f}'.rstrip('0').rstrip('.') if value < 10 else f'{value:.0f}'
    return text.replace('.', ',') + ' m'


# ---------------------------------------------------------------------------
# Esri World Imagery / Wayback
# ---------------------------------------------------------------------------

def _wayback_releases():
    try:
        return imagery_service.wayback_releases()
    except (ImageryError, ValueError, requests.RequestException):
        return []


def esri_captures(metadata_url, bounds, zoom):
    """Capturas (satélite, data, resolução) que formam a imagem da Esri na área.

    As camadas do serviço de metadados vão de 0 (zoom 23) a 13 (zoom ≤ 10),
    como em `maps.js`; sem imagem naquele nível, tenta os dois mais grosseiros.
    """
    if not metadata_url:
        return []
    minx, miny, maxx, maxy = bounds
    first = max(0, min(13, 23 - round(zoom)))
    for layer in range(first, min(13, first + 2) + 1):
        try:
            response = requests.get(f'{metadata_url}/{layer}/query', params={
                'f': 'json',
                'geometry': f'{minx},{miny},{maxx},{maxy}',
                'geometryType': 'esriGeometryEnvelope',
                'inSR': '4326',
                'spatialRel': 'esriSpatialRelIntersects',
                'returnGeometry': 'false',
                'outFields': ESRI_FIELDS,
            }, timeout=TIMEOUT)
            features = response.json().get('features') or []
        except (requests.RequestException, ValueError):
            return []
        if features:
            return _captures([f.get('attributes') or {} for f in features])
    return []


def _captures(attributes):
    seen, captures = set(), []
    for a in attributes:
        code = (a.get('SRC_DESC') or '').strip()
        provider = (a.get('NICE_DESC') or '').strip()
        when = a.get('SRC_DATE2')
        day = datetime.fromtimestamp(when / 1000, tz=timezone.utc).date().isoformat() if when else ''
        satellite = SENSORS.get(code.upper(), code)
        key = (satellite, provider, day)
        if key in seen:
            continue
        seen.add(key)
        captures.append({
            'satelite': satellite or None,
            'provedor': provider if provider and provider != satellite else None,
            'data_captura': _br_date(day) or None,
            'resolucao_m': round(a['SRC_RES'], 2) if a.get('SRC_RES') else None,
            'precisao_m': round(a['SRC_ACC'], 1) if a.get('SRC_ACC') else None,
            '_dia': day,
        })
    captures.sort(key=lambda c: c['_dia'], reverse=True)
    for capture in captures:
        capture.pop('_dia')
    return captures[:MAX_CAPTURES]


def _capture_text(capture):
    who = capture['satelite'] or 'satélite não informado'
    if capture.get('provedor'):
        who += f" ({capture['provedor']})"
    parts = [who]
    if capture.get('data_captura'):
        parts.append(f"captura de {capture['data_captura']}")
    if capture.get('resolucao_m'):
        parts.append(_meters(capture['resolucao_m']))
    return ', '.join(parts)


class EsriBasemap(Basemap):
    """World Imagery da Esri numa versão da Wayback (a mais recente = imagem atual)."""
    attribution = 'Imagens: Esri, Maxar, Earthstar Geographics'

    def __init__(self, release=None, requested_year=None):
        self.release = release
        self.requested_year = requested_year
        if release:
            self.url = WAYBACK_TILE_URL.replace('{release}', str(release['id']))
        else:
            self.url = static_map.ESRI_IMAGERY_URL

    def tile(self, session, zoom, x, y):
        return static_map._fetch_tile(session, self.url, zoom, x, y)

    def describe(self, geom, zoom, left, top):
        release = self.release or {}
        captures = esri_captures(release.get('metadata_url'), geom.bounds, zoom)
        version = _br_date(release.get('date')) if release else None
        fonte = {
            'tipo': 'satelite' if self.requested_year is None else 'satelite_historico',
            'provedor': 'Esri World Imagery' + (f' (versão da Esri Wayback de {version})' if version else ''),
            'capturas': captures,
        }
        if captures:
            resolutions = [c['resolucao_m'] for c in captures if c['resolucao_m']]
            fonte['resolucao_m'] = min(resolutions) if resolutions else None
            fonte['descricao'] = '; '.join(_capture_text(c) for c in captures) + f" — {fonte['provedor']}"
        else:
            fonte['descricao'] = (f"{fonte['provedor']}: mosaico de satélites; a Esri não informou "
                                  'o satélite nem a data da captura para esta área.')
        if self.requested_year:
            fonte['ano_pedido'] = self.requested_year
            years = {int(c['data_captura'][-4:]) for c in captures if c.get('data_captura')}
            if years and self.requested_year not in years:
                fonte['observacao'] = (
                    f'A versão de {self.requested_year} da Esri mostra, nesta área, imagem de '
                    f'{", ".join(str(y) for y in sorted(years))}: a Esri só troca a imagem quando recebe uma nova captura.')
        return fonte

    def source_lines(self, fonte):
        lines = [_capture_text(c) for c in fonte.get('capturas') or []]
        lines.append(fonte['provedor'] if lines else fonte['descricao'])
        return lines


def current_satellite():
    releases = _wayback_releases()
    return EsriBasemap(releases[0]) if releases else static_map.BASEMAPS['satelite']()


def wayback_for_year(year):
    """Última versão da Wayback publicada até o fim do ano pedido."""
    releases = [r for r in _wayback_releases() if r['date'] <= f'{year}-12-31']
    if not releases:
        raise MapRenderError('A Esri Wayback não respondeu. Tente de novo em alguns minutos.')
    return EsriBasemap(releases[0], requested_year=year)


# ---------------------------------------------------------------------------
# Landsat 4/5/7 (1984–2012)
# ---------------------------------------------------------------------------

def _day_of_year(day):
    try:
        return date.fromisoformat(day).timetuple().tm_yday
    except ValueError:
        return REFERENCE_DAY_OF_YEAR


def _landsat_scene(scene):
    satellite, sensor = LANDSAT_PLATFORMS.get(scene['platform'], (scene['platform'], ''))
    return {
        'cena': scene['id'],
        'satelite': satellite,
        'sensor': sensor,
        'data_captura': _br_date(scene['date']),
        'nuvens_na_cena_pct': scene['cloud'],
    }


def choose_landsat_scene(lon, lat, year, scene_id=None):
    """(cena escolhida, outras cenas do ano), do acervo do Planetary Computer.

    Sem `scene_id`: a de menos nuvem no ano (Landsat 7 depois de 2003 perde
    pontos, pelas faixas sem dado); no empate, a mais perto de julho.
    """
    try:
        scenes = imagery_service.landsat_legacy_scenes(lon, lat)
    except ImageryError as exc:
        raise MapRenderError(f'{exc} Tente de novo em alguns minutos.') from None
    of_year = [s for s in scenes if s['date'][:4] == str(year)]
    if scene_id:
        chosen = next((s for s in scenes if s['id'] == scene_id), None)
        if chosen is None:
            raise MapRenderError(f'A cena {scene_id} não cobre esta área. Use uma das listadas em outras_cenas_do_ano.')
        year_scenes = [s for s in scenes if s['date'][:4] == chosen['date'][:4]]
        return chosen, [s for s in year_scenes if s is not chosen]
    if not of_year:
        anos = sorted({s['date'][:4] for s in scenes})
        perto = sorted(anos, key=lambda a: abs(int(a) - year))[:3]
        raise MapRenderError(
            f'Não há cena Landsat de {year} com menos de 40% de nuvens sobre a área.'
            + (f' Anos mais próximos com imagem: {", ".join(sorted(perto))}.' if perto else ''))
    chosen = min(of_year, key=lambda s: (imagery_service._landsat_legacy_rank(s),
                                        abs(_day_of_year(s['date']) - REFERENCE_DAY_OF_YEAR)))
    return chosen, [s for s in of_year if s is not chosen]


class LandsatBasemap(Basemap):
    max_zoom = LANDSAT_LEGACY_ENHANCED_MAX_ZOOM
    attribution = 'Landsat: USGS/NASA, via Microsoft Planetary Computer'
    unavailable = 'O acervo do Landsat (Planetary Computer) não respondeu. Tente de novo em alguns minutos.'

    def __init__(self, scene, composition='natural', others=()):
        if composition not in LANDSAT_LEGACY_COMPOSITIONS:
            raise MapRenderError(f'Composição inválida. Use uma destas: {", ".join(LANDSAT_LEGACY_COMPOSITIONS)}.')
        self.scene, self.composition, self.others = scene, composition, list(others)

    def tile(self, session, zoom, x, y):
        try:
            # Com o realce da tela ("Melhorar imagem"): contraste da cena e nitidez.
            found = imagery_service.landsat_legacy_tile(self.scene['id'], self.composition, zoom, x, y, enhance=True)
        except ImageryError:
            return None
        return Image.open(io.BytesIO(found[0])) if found else None

    def describe(self, geom, zoom, left, top):
        scene = _landsat_scene(self.scene)
        fonte = {
            'tipo': 'satelite_historico',
            **scene,
            'resolucao_m': 30,
            'composicao': LANDSAT_LEGACY_COMPOSITIONS[self.composition]['label'],
            'provedor': LANDSAT_PROVIDER,
            'outras_cenas_do_ano': [_landsat_scene(s) for s in self.others],
            'descricao': (f"{scene['satelite']} (sensor {scene['sensor']}), captura de {scene['data_captura']}, "
                          f"30 m, {scene['nuvens_na_cena_pct']}% de nuvens na cena — {LANDSAT_PROVIDER}"),
        }
        if self.scene['platform'] == 'landsat-7' and int(self.scene['date'][:4]) >= LANDSAT7_SLC_OFF_YEAR:
            fonte['observacao'] = ('Landsat 7 depois de 31/05/2003 tem faixas diagonais sem dado (falha do SLC); '
                                   'se cortarem o imóvel, peça outra cena do ano.')
        return fonte

    def source_lines(self, fonte):
        return [
            f"{fonte['satelite']} (sensor {fonte['sensor']}), captura de {fonte['data_captura']}",
            f"30 m · {fonte['composicao']} · {fonte['nuvens_na_cena_pct']}% de nuvens na cena",
            f"Cena {fonte['cena']}",
            LANDSAT_PROVIDER,
        ]


# ---------------------------------------------------------------------------
# MapBiomas (cobertura e uso da terra)
# ---------------------------------------------------------------------------

CLASS_NAMES = {code: (name, color) for code, name, color in raster_tiles.MAPBIOMAS_CLASSES}


class LandUseBasemap(Basemap):
    """Classes do MapBiomas lidas numa janela só do GeoTIFF (sem montar tiles)."""
    min_zoom = raster_tiles.MAPBIOMAS_MIN_ZOOM
    resample = Image.NEAREST
    unavailable = 'O GeoTIFF do MapBiomas não respondeu. Tente de novo em alguns minutos.'

    def __init__(self, year, area_ha=None):
        first, last = raster_tiles.MAPBIOMAS_PRODUCTS[MAPBIOMAS_PRODUCT]['years']
        if not first <= year <= last:
            raise MapRenderError(f'O MapBiomas tem uso do solo de {first} a {last}.')
        self.year, self.area_ha, self.codes = year, area_ha, None
        self.product_name = raster_tiles.MAPBIOMAS_PRODUCTS[MAPBIOMAS_PRODUCT]['name']
        self.attribution = f'MapBiomas Coleção 11 – {year}'

    def window(self, zoom, left, top, width, height):
        pixel = 2 * EARTH_HALF / (static_map.TILE_SIZE * 2 ** zoom)
        origin = (left * pixel - EARTH_HALF, EARTH_HALF - top * pixel)
        url = raster_tiles.MAPBIOMAS_PRODUCTS[MAPBIOMAS_PRODUCT]['url'].format(year=self.year)
        try:
            codes = raster_tiles._warp_window(url, origin, pixel, width, height, 'NearestNeighbour')[0]
        except ImageryError:
            raise MapRenderError(self.unavailable) from None
        self.codes = np.asarray(codes)
        palette = raster_tiles._mapbiomas_palette(MAPBIOMAS_PRODUCT, self.codes)
        classes = Image.open(io.BytesIO(raster_tiles._palette_png(self.codes, palette))).convert('RGBA')
        image = Image.new('RGBA', (width, height), (235, 235, 230, 255))
        image.alpha_composite(classes)
        return image

    def describe(self, geom, zoom, left, top):
        fonte = {
            'tipo': 'uso_do_solo',
            'produto': self.product_name,
            'ano': self.year,
            'resolucao_m': 30,
            'origem_dos_dados': 'classificação anual de imagens Landsat (30 m) feita pelo projeto MapBiomas',
            'provedor': 'Projeto MapBiomas',
            'classes_no_imovel': self._shares(geom, zoom, left, top),
            'descricao': f'{self.product_name}, ano {self.year} (classificação de imagens Landsat, 30 m)',
        }
        return fonte

    def _shares(self, geom, zoom, left, top):
        if self.codes is None:
            return []
        height, width = self.codes.shape
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)

        def project(coords):
            return [(x - left, y - top) for x, y in (static_map.world_pixel(c[0], c[1], zoom) for c in coords)]

        for polygon in static_map._parts(geom, 'Polygon'):
            draw.polygon(project(polygon.exterior.coords), fill=1)
            for hole in polygon.interiors:
                draw.polygon(project(hole.coords), fill=0)
        inside = self.codes[np.asarray(mask, dtype=bool)]
        inside = inside[inside > 0]
        if not inside.size:
            return []
        counts = np.bincount(inside.astype(np.int64))
        shares = []
        for code in np.nonzero(counts)[0].tolist():
            pct = counts[code] * 100 / inside.size
            name, color = CLASS_NAMES.get(code, (f'Classe {code}', raster_tiles.UNKNOWN_CLASS_COLOR))
            entry = {'classe': name, 'cor': color, 'percentual': round(pct, 1)}
            if self.area_ha:
                entry['area_ha'] = round(self.area_ha * pct / 100, 2)
            shares.append(entry)
        shares.sort(key=lambda s: -s['percentual'])
        return shares

    def legend_rows(self, fonte):
        rows = []
        for share in fonte.get('classes_no_imovel') or []:
            if share['percentual'] < MIN_CLASS_PCT or len(rows) >= MAX_CLASSES_IN_LEGEND:
                continue
            detail = f"{share['percentual']:.1f}% do imóvel".replace('.', ',')
            if share.get('area_ha') is not None:
                detail += ' · ' + f"{share['area_ha']:,.2f} ha".replace(',', 'X').replace('.', ',').replace('X', '.')
            rows.append((share['cor'], share['classe'], detail))
        return rows

    def source_lines(self, fonte):
        return [f'{self.product_name}, ano {self.year}', 'Classificação de imagens Landsat (30 m), projeto MapBiomas']


# ---------------------------------------------------------------------------
# Escolha do fundo
# ---------------------------------------------------------------------------

def year_range_text():
    first, last = LANDSAT_LEGACY_YEARS
    return f'{first}–{last} (Landsat, 30 m) ou {WAYBACK_FIRST_YEAR} em diante (Esri, alta resolução)'


def historical(year, lon, lat, composition='natural', scene_id=None):
    """Fundo com a imagem de satélite de `year` sobre o ponto (lon, lat)."""
    first, last = LANDSAT_LEGACY_YEARS
    if scene_id or first <= year <= last:
        chosen, others = choose_landsat_scene(lon, lat, year, scene_id)
        return LandsatBasemap(chosen, composition, others)
    if WAYBACK_FIRST_YEAR <= year <= date.today().year:
        return wayback_for_year(year)
    raise MapRenderError(f'Não há imagem de {year} aqui. Anos disponíveis: {year_range_text()}.')


def image_label(basemap):
    """O que o fundo mostra, para o subtítulo do mapa (vazio no satélite atual e no mapa)."""
    if isinstance(basemap, LandsatBasemap):
        scene = _landsat_scene(basemap.scene)
        return f"{scene['satelite']} de {scene['data_captura']}"
    if isinstance(basemap, LandUseBasemap):
        return f'Uso do solo MapBiomas {basemap.year}'
    if isinstance(basemap, EsriBasemap) and basemap.requested_year:
        return f'Imagem Esri (versão de {basemap.requested_year})'
    return ''


def basemap_for(spec, geom=None, area_ha=None):
    """`Basemap` de um fundo: 'satelite', 'mapa' ou um dict
    {'tipo': 'historica', 'ano', 'composicao', 'cena'} / {'tipo': 'uso_solo', 'ano'}."""
    if not spec or spec == 'satelite':
        return current_satellite()
    if isinstance(spec, str):
        if spec in static_map.BASEMAPS:
            return static_map.BASEMAPS[spec]()
        raise MapRenderError('Fundo inválido. Use "satelite" ou "mapa".')
    if spec.get('tipo') == 'uso_solo':
        return LandUseBasemap(int(spec['ano']), area_ha)
    if spec.get('tipo') == 'historica':
        center = geom.centroid
        return historical(int(spec['ano']), center.x, center.y, spec.get('composicao') or 'natural', spec.get('cena'))
    raise MapRenderError('Fundo inválido.')
