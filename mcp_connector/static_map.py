"""Imagem estática do mapa de uma análise (o "print do mapa" do conector).

Desenha, sobre a imagem de satélite da Esri (a mesma camada pública do mapa
de resultados), o contorno do imóvel e os recortes das bases, com título,
legenda e escala. Roda no servidor, sem navegador: os tiles são baixados e
montados com o Pillow.
"""
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape

TILE_SIZE = 256
TIMEOUT = 15
MAX_ZOOM = 17
MIN_ZOOM = 3
WIDTH, HEIGHT = 1400, 900
HEADER_HEIGHT = 74
# Legenda num painel à direita, fora do mapa, para não cobrir o imóvel.
PANEL_WIDTH = 380
MAP_WIDTH, MAP_HEIGHT = WIDTH - PANEL_WIDTH, HEIGHT - HEADER_HEIGHT
# Folga entre o imóvel e a borda do mapa.
PADDING = 60
MAX_LEGEND_ROWS = 14
PROPERTY_COLOR = '#FFD400'
FILL_ALPHA = 105
BASEMAPS = {
    'satelite': (
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'Imagens: Esri, Maxar, Earthstar Geographics',
    ),
    'mapa': (
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
        'Mapa: Esri, HERE, Garmin, OpenStreetMap',
    ),
}
# Cores para os itens de uma base só (cada zona, cada CAR vizinho...).
ITEM_PALETTE = (
    '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4',
    '#f032e6', '#bfef45', '#fabed4', '#469990', '#dcbeff', '#9a6324',
)


class MapRenderError(Exception):
    pass


def _font(size, bold=False):
    names = ('DejaVuSans-Bold.ttf', 'arialbd.ttf') if bold else ('DejaVuSans.ttf', 'arial.ttf')
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _rgb(color):
    color = (color or '#9E9E9E').lstrip('#')
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (158, 158, 158)


def world_pixel(lon, lat, zoom):
    """Posição do ponto em pixels no mundo Web Mercator do zoom dado."""
    size = TILE_SIZE * 2 ** zoom
    lat = max(min(lat, 85.0511), -85.0511)
    sin = math.sin(math.radians(lat))
    x = (lon + 180) / 360 * size
    y = (0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)) * size
    return x, y


def fit_zoom(bounds, width=MAP_WIDTH, height=MAP_HEIGHT):
    """Maior zoom em que a área cabe no mapa com a folga."""
    minx, miny, maxx, maxy = bounds
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        x0, y1 = world_pixel(minx, miny, zoom)
        x1, y0 = world_pixel(maxx, maxy, zoom)
        if x1 - x0 <= width - 2 * PADDING and y1 - y0 <= height - 2 * PADDING:
            return zoom
    return MIN_ZOOM


def frame(bounds, width=MAP_WIDTH, height=MAP_HEIGHT):
    """Zoom dos tiles e a redução que faz a área ocupar o mapa (zoom fracionário).

    Com o zoom inteiro a área pode ficar com metade do tamanho possível; aí os
    tiles vêm do zoom seguinte e são reduzidos por `escala` (entre 0,5 e 1).
    """
    zoom = fit_zoom(bounds, width, height)
    minx, miny, maxx, maxy = bounds
    x0, y1 = world_pixel(minx, miny, zoom)
    x1, y0 = world_pixel(maxx, maxy, zoom)
    room = min((width - 2 * PADDING) / max(x1 - x0, 1), (height - 2 * PADDING) / max(y1 - y0, 1))
    if zoom < MAX_ZOOM and room >= 1.15:
        return zoom + 1, min(room, 2) / 2
    return zoom, 1.0


def _fetch_tile(session, url, zoom, x, y):
    limit = 2 ** zoom
    if not 0 <= y < limit:
        return None
    try:
        response = session.get(url.format(z=zoom, x=x % limit, y=y), timeout=TIMEOUT)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert('RGB')
    except Exception:
        return None


def _basemap(url, zoom, left, top, width, height):
    image = Image.new('RGB', (width, height), (205, 205, 200))
    tiles = [
        (tx, ty)
        for tx in range(math.floor(left / TILE_SIZE), math.floor((left + width - 1) / TILE_SIZE) + 1)
        for ty in range(math.floor(top / TILE_SIZE), math.floor((top + height - 1) / TILE_SIZE) + 1)
    ]
    with requests.Session() as session, ThreadPoolExecutor(max_workers=8) as pool:
        session.headers['User-Agent'] = 'TerraView-Tocantins/1.0 (mapa do conector)'
        fetched = list(pool.map(lambda t: _fetch_tile(session, url, zoom, *t), tiles))
    if not any(fetched):
        raise MapRenderError('O servidor de imagens de satélite não respondeu. Tente de novo em alguns minutos.')
    for (tx, ty), tile in zip(tiles, fetched):
        if tile is not None:
            image.paste(tile, (round(tx * TILE_SIZE - left), round(ty * TILE_SIZE - top)))
    return image


def _parts(geom, kind):
    if geom.is_empty:
        return []
    if geom.geom_type.startswith('Multi') or geom.geom_type == 'GeometryCollection':
        return [p for g in geom.geoms for p in _parts(g, kind)]
    return [geom] if kind in geom.geom_type else []


class _Projector:
    def __init__(self, zoom, left, top, scale=1.0):
        self.zoom, self.left, self.top, self.scale = zoom, left, top, scale

    def __call__(self, coords):
        points = []
        for coord in coords:
            x, y = world_pixel(coord[0], coord[1], self.zoom)
            points.append(((x - self.left) * self.scale, (y - self.top) * self.scale))
        return points


def _draw_geometry(fill_layer, line_layer, geom, project, color, width=3, fill=True):
    rgb = _rgb(color)
    if fill:
        mask = Image.new('L', fill_layer.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        for polygon in _parts(geom, 'Polygon'):
            mask_draw.polygon(project(polygon.exterior.coords), fill=255)
            for hole in polygon.interiors:
                mask_draw.polygon(project(hole.coords), fill=0)
        fill_layer.paste(rgb + (FILL_ALPHA,), (0, 0, *fill_layer.size), mask)
    draw = ImageDraw.Draw(line_layer)
    for polygon in _parts(geom, 'Polygon'):
        for ring in (polygon.exterior, *polygon.interiors):
            draw.line(project(ring.coords), fill=rgb + (255,), width=width, joint='curve')
    for line in _parts(geom, 'LineString'):
        draw.line(project(line.coords), fill=rgb + (255,), width=width + 1, joint='curve')
    for point in _parts(geom, 'Point'):
        (x, y), = project(point.coords)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=rgb + (255,), outline=(255, 255, 255, 255), width=2)


def _scale_bar(draw, meters_per_px, right, bottom, font):
    target = meters_per_px * 180
    magnitude = 10 ** math.floor(math.log10(target))
    meters = max(m * magnitude for m in (1, 2, 5) if m * magnitude <= target)
    length = meters / meters_per_px
    label = f'{meters / 1000:g} km' if meters >= 1000 else f'{meters:g} m'
    x0 = right - length
    draw.rectangle((x0 - 10, bottom - 34, right + 10, bottom + 8), fill=(255, 255, 255, 215))
    draw.line((x0, bottom, right, bottom), fill=(20, 20, 20, 255), width=4)
    for x in (x0, right):
        draw.line((x, bottom - 8, x, bottom), fill=(20, 20, 20, 255), width=3)
    draw.text(((x0 + right) / 2, bottom - 12), label, fill=(20, 20, 20, 255), font=font, anchor='ms')


def _wrap(draw, text, font, width, max_lines=2):
    words, lines = str(text).split(), []
    for word in words:
        if lines and draw.textlength(f'{lines[-1]} {word}', font=font) <= width:
            lines[-1] = f'{lines[-1]} {word}'
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip('.,;') + '…'
    return lines


def _panel(draw, rows, notes, attribution):
    """Legenda, notas e créditos no painel à direita do mapa."""
    x0, x1 = MAP_WIDTH + 22, WIDTH - 20
    text_x, text_width = x0 + 36, x1 - x0 - 36
    label_font, detail_font = _font(16), _font(14)
    draw.text((x0, HEADER_HEIGHT + 22), 'Legenda', fill=(25, 25, 25), font=_font(19, bold=True))
    rows = list(rows)
    if len(rows) > MAX_LEGEND_ROWS:
        hidden = len(rows) - (MAX_LEGEND_ROWS - 1)
        rows = rows[:MAX_LEGEND_ROWS - 1] + [(None, f'+ {hidden} outros itens', 'veja arquivos_analise')]
    y = HEADER_HEIGHT + 60
    for color, label, detail in rows:
        if color == 'imovel':
            draw.rectangle((x0, y + 2, x0 + 24, y + 18), outline=_rgb(PROPERTY_COLOR), width=4)
        elif color:
            draw.rectangle((x0, y + 2, x0 + 24, y + 18), fill=_rgb(color), outline=(40, 40, 40), width=1)
        for line in _wrap(draw, label, label_font, text_width):
            draw.text((text_x, y), line, fill=(25, 25, 25), font=label_font)
            y += 20
        if detail:
            draw.text((text_x, y), detail, fill=(95, 95, 95), font=detail_font)
            y += 18
        y += 10

    small = _font(13)
    note_lines = [line for note in notes for line in _wrap(draw, note, small, x1 - x0, max_lines=4)]
    y = max(y + 6, HEIGHT - 34 - 17 * len(note_lines))
    for line in note_lines:
        draw.text((x0, y), line, fill=(70, 70, 70), font=small)
        y += 17
    draw.text((x0, HEIGHT - 14), attribution, fill=(120, 120, 120), font=_font(12), anchor='ls')


def _geometry(value):
    if not value:
        return None
    try:
        geom = shape(json.loads(value) if isinstance(value, str) else value)
    except Exception:
        return None
    return None if geom.is_empty else geom


def render_map(property_geojson, layers, title, subtitle='', basemap='satelite',
               property_label='Imóvel analisado', notes=()):
    """PNG do mapa.

    `layers`: [{'label', 'color', 'detail', 'geometries': [GeoJSON (dict ou texto)]}],
    desenhadas na ordem (a última fica por cima). `notes`: frases no rodapé da legenda.
    """
    if basemap not in BASEMAPS:
        raise MapRenderError(f'Fundo inválido. Use um destes: {", ".join(BASEMAPS)}.')
    prop = _geometry(property_geojson)
    if prop is None:
        raise MapRenderError('A análise não tem o contorno da área analisada.')
    layers = [
        {**layer, 'shapes': [g for g in map(_geometry, layer.get('geometries') or []) if g is not None]}
        for layer in layers
    ]
    layers = [layer for layer in layers if layer['shapes']]

    zoom, scale = frame(prop.bounds)
    minx, miny, maxx, maxy = prop.bounds
    x0, y1 = world_pixel(minx, miny, zoom)
    x1, y0 = world_pixel(maxx, maxy, zoom)
    # Recorte no zoom dos tiles, reduzido depois para o tamanho do mapa.
    source_width, source_height = math.ceil(MAP_WIDTH / scale), math.ceil(MAP_HEIGHT / scale)
    left = round((x0 + x1) / 2 - source_width / 2)
    top = round((y0 + y1) / 2 - source_height / 2)
    url, attribution = BASEMAPS[basemap]
    map_image = _basemap(url, zoom, left, top, source_width, source_height)
    if map_image.size != (MAP_WIDTH, MAP_HEIGHT):
        map_image = map_image.resize((MAP_WIDTH, MAP_HEIGHT), Image.LANCZOS)
    map_image = map_image.convert('RGBA')
    project = _Projector(zoom, left, top, MAP_WIDTH / source_width)

    fill_layer = Image.new('RGBA', map_image.size, (0, 0, 0, 0))
    line_layer = Image.new('RGBA', map_image.size, (0, 0, 0, 0))
    for layer in layers:
        for geom in layer['shapes']:
            _draw_geometry(fill_layer, line_layer, geom, project, layer['color'], width=2)
    # Contorno do imóvel por cima de tudo, com sombra para destacar no satélite.
    _draw_geometry(fill_layer, line_layer, prop, project, '#000000', width=7, fill=False)
    _draw_geometry(fill_layer, line_layer, prop, project, PROPERTY_COLOR, width=3, fill=False)
    map_image = Image.alpha_composite(Image.alpha_composite(map_image, fill_layer), line_layer)

    overlay = Image.new('RGBA', map_image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Norte para cima.
    nx, ny = MAP_WIDTH - 42, 22
    draw.polygon(((nx, ny), (nx - 11, ny + 30), (nx + 11, ny + 30)), fill=(255, 255, 255, 235), outline=(20, 20, 20, 255))
    draw.text((nx, ny + 46), 'N', fill=(255, 255, 255, 255), font=_font(18, bold=True), anchor='mm',
              stroke_width=2, stroke_fill=(20, 20, 20, 255))
    meters_per_px = 156543.03392 * math.cos(math.radians((miny + maxy) / 2)) / 2 ** zoom * source_width / MAP_WIDTH
    _scale_bar(draw, meters_per_px, MAP_WIDTH - 24, MAP_HEIGHT - 20, _font(15))
    map_image = Image.alpha_composite(map_image, overlay).convert('RGB')

    image = Image.new('RGB', (WIDTH, HEIGHT), (255, 255, 255))
    image.paste(map_image, (0, HEADER_HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEADER_HEIGHT), fill=(22, 36, 30))
    draw.text((20, 14), title, fill=(255, 255, 255), font=_font(26, bold=True))
    if subtitle:
        draw.text((20, 46), subtitle, fill=(215, 225, 218), font=_font(17))
    draw.line((MAP_WIDTH, HEADER_HEIGHT, MAP_WIDTH, HEIGHT), fill=(210, 210, 210), width=1)
    rows = [('imovel', property_label, '')] + [(layer['color'], layer['label'], layer.get('detail') or '') for layer in layers]
    _panel(draw, rows, notes, attribution)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def to_jpeg(png_bytes, quality=85):
    """Versão leve da imagem para devolver dentro da conversa."""
    buffer = io.BytesIO()
    Image.open(io.BytesIO(png_bytes)).convert('RGB').save(buffer, format='JPEG', quality=quality, optimize=True)
    return buffer.getvalue()
