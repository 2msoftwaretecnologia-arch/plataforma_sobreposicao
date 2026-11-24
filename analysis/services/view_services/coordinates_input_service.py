"""Área do imóvel digitada como lista de vértices (um por linha).

Aceita graus decimais (`-10.1873, -48.3336`, `-10,1873; -48,3336`) e graus,
minutos e segundos (`10°11'14,3" S 48°20'01,0" W`), em qualquer ordem
(lat/lon ou lon/lat) — os dois jeitos que o Google Maps copia. A ordem é
deduzida pelo tamanho: no Brasil a latitude nunca passa de 34° e a longitude
nunca fica abaixo disso. Sem hemisfério (N/S/L/O),
o valor é tratado como sul/oeste, onde fica o Tocantins, com ou sem o sinal.

Em UTM (SIRGAS 2000, hemisfério sul) o fuso vem à parte, escolhido no
formulário (`utm_zone`): cada linha traz o E e o N em metros, em qualquer
ordem (o N, na casa dos milhões, é o maior). Números abaixo de 100 000 (nome
do vértice, altitude) são ignorados.

Uma coordenada só é um ponto: a análise vai para o imóvel do SICAR que o
contém (ver `UploadZipCarView._handle_coordinates_input`).

O mesmo leitor existe em `bases_3d.js` (`parseCoordinates`) para a
pré-visualização no mapa; este é o que vale para a análise.
"""
import re

from django.contrib.gis.geos import GEOSGeometry
from pyproj import Transformer
from shapely.geometry import Polygon

SRID = 4674
# Fusos UTM do Brasil; SIRGAS 2000 / UTM <fuso>S = EPSG 31960 + fuso.
UTM_ZONES = range(18, 26)

_DMS_RE = re.compile(
    r"(-)?\s*(\d{1,3})\s*[°º]\s*(\d{1,2})\s*['’′]\s*(?:(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|''|”|″)?)?\s*([NSEWOL])?",
    re.I,
)
_DECIMAL_RE = re.compile(r'-?\d+(?:[.,]\d+)?')
# Metros com ou sem separador de milhar: 785123.45, 785123,45 ou 785.123,45.
_METERS_RE = re.compile(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?')


class CoordinatesInputError(ValueError):
    pass


def _dms_values(line):
    """[(valor com sinal, hemisfério ou '')] dos campos em graus/min/seg da linha."""
    values = []
    for sign, deg, minutes, seconds, hemi in _DMS_RE.findall(line):
        value = int(deg) + int(minutes) / 60 + float((seconds or '0').replace(',', '.')) / 3600
        hemi = hemi.upper()
        if sign or hemi in ('S', 'W', 'O'):
            value = -value
        values.append((value, hemi))
    return values


def _decimal_values(line):
    return [(float(n.replace(',', '.')), '') for n in _DECIMAL_RE.findall(line)]


def _vertex(line, number):
    values = _dms_values(line) if re.search(r'[°º]', line) else _decimal_values(line)
    if len(values) not in (2, 3):  # a 3ª é a altitude, ignorada
        raise CoordinatesInputError(f'Linha {number}: esperava latitude e longitude, achei "{line.strip()}".')
    # Sem hemisfério, sul/oeste (o sinal digitado não muda nada no Brasil).
    (a, ha), (b, hb) = [(v if h else -abs(v), h) for v, h in values[:2]]

    if ha in ('E', 'W', 'O', 'L') or hb in ('N', 'S'):
        a, b = b, a
    elif not (ha in ('N', 'S') or hb in ('E', 'W', 'O', 'L')) and abs(a) > abs(b):
        a, b = b, a
    lat, lon = a, b

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        if max(abs(lat), abs(lon)) >= 1000:
            raise CoordinatesInputError(
                f'Linha {number}: "{line.strip()}" parece estar em UTM; escolha o formato UTM e o fuso.')
        raise CoordinatesInputError(f'Linha {number}: coordenada fora do intervalo ("{line.strip()}").')
    return lon, lat


def _meters(token):
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?', token):
        token = token.replace('.', '')
    return float(token.replace(',', '.'))


def _utm_vertex(line, number, transformer):
    values = [v for v in map(_meters, _METERS_RE.findall(line)) if v >= 100_000]
    if len(values) != 2:
        raise CoordinatesInputError(f'Linha {number}: esperava E e N em UTM (metros), achei "{line.strip()}".')
    east, north = sorted(values)
    if not (100_000 <= east <= 900_000 and north <= 10_000_000):
        raise CoordinatesInputError(f'Linha {number}: coordenada UTM fora do intervalo ("{line.strip()}").')
    lon, lat = transformer.transform(east, north)
    return lon, lat


def utm_transformer(zone):
    try:
        zone = int(zone)
    except (TypeError, ValueError):
        zone = 0
    if zone not in UTM_ZONES:
        raise CoordinatesInputError('Escolha o fuso UTM (18 a 25).')
    return Transformer.from_crs(31960 + zone, SRID, always_xy=True)


def parse_vertices(text: str, utm_zone=None) -> list:
    """[(lon, lat)] na ordem digitada, sem repetidos seguidos nem o fechamento do anel.

    Com `utm_zone` (fuso, hemisfério sul), as linhas são E/N em UTM."""
    transformer = utm_transformer(utm_zone) if utm_zone is not None else None
    vertices = []
    for number, line in enumerate((text or '').splitlines(), start=1):
        if not line.strip():
            continue
        vertex = _utm_vertex(line, number, transformer) if transformer else _vertex(line, number)
        if not vertices or vertices[-1] != vertex:
            vertices.append(vertex)
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices.pop()  # quem fecha o anel é a gente
    if not vertices:
        raise CoordinatesInputError('Informe ao menos uma coordenada.')
    return vertices


def build_polygon(vertices: list) -> GEOSGeometry:
    """Polígono (SIRGAS 2000) com os vértices na ordem em que vieram."""
    if len(vertices) < 3:
        raise CoordinatesInputError(
            'Informe 1 coordenada (para achar o imóvel do ponto) ou pelo menos 3 vértices (para uma área).')

    polygon = Polygon(vertices)
    if polygon.minimum_rotated_rectangle.area == 0:
        raise CoordinatesInputError('Os vértices estão alinhados e não formam uma área.')
    if not polygon.is_valid:
        raise CoordinatesInputError('O contorno se cruza: confira se os vértices estão na ordem do perímetro.')

    geometry = GEOSGeometry(polygon.wkt)
    geometry.srid = SRID
    return geometry
