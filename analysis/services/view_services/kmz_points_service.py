"""Localiza em quais imóveis do SICAR caem os pontos de um KMZ/KML.

Os arquivos de "localização" chegam do Google Earth com um Placemark por
ponto, cada um com um `Point` (o centro) e um `LinearRing` (o quadrado de
~60 ha gerado em volta). Para descobrir o imóvel usamos só o ponto central —
o quadrado é ignorado; quando o Placemark não tiver `Point`, o centro do
polígono é usado no lugar.

Alguns Placemarks vêm sem geometria nenhuma, só com o nome — um Plus Code
curto do Google ("2Q4W+XF Natal, Araguatins - TO, Brasil"). Esses são
recuperados usando como referência os pontos com coordenada da mesma
localidade no próprio arquivo.
"""
import io
import json
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from django.db import connection
from shapely.geometry import Polygon


# Acima disso o ponto do arquivo e o Plus Code do nome são tratados como
# localizações diferentes.
DIVERGENCE_LIMIT_M = 200


class KmzPointsError(ValueError):
    pass


@dataclass
class LocationPoint:
    index: int
    name: str
    lon: float
    lat: float
    source: str = ''
    from_plus_code: bool = False
    # Distância (m) entre o ponto do arquivo e o Plus Code do nome. Quando o
    # Google Earth não consegue geocodificar o endereço ele joga o ponto no
    # centro da cidade (ou numa cidade homônima de outro estado), e aí o ponto
    # e o código do nome não batem. Nesses casos a posição usada é a do Plus
    # Code, que é o endereço original (ver `parse_location_points`).
    divergence_m: float = None
    cars: list = field(default_factory=list)

    @property
    def is_divergent(self) -> bool:
        return self.divergence_m is not None and self.divergence_m > DIVERGENCE_LIMIT_M


# ---------------------------------------------------------------------------
# Plus Codes (Open Location Code) — só o necessário para recuperar um código
# curto a partir de uma referência próxima (algoritmo `recoverNearest`).
# ---------------------------------------------------------------------------
_OLC_ALPHABET = '23456789CFGHJMPQRVWX'
_OLC_PAIR_RESOLUTIONS = [20.0, 1.0, 0.05, 0.0025, 0.000125]
_PLUS_CODE_RE = re.compile(r'^\s*([23456789CFGHJMPQRVWX]{2,8}\+[23456789CFGHJMPQRVWX]{0,3})\s*(.*)$', re.I)


def _olc_prefix(lat: float, lng: float, length: int) -> str:
    lat = min(max(lat, -90.0), 90.0 - 1e-9) + 90.0
    lng = ((lng + 180.0) % 360.0)
    code = ''
    for res in _OLC_PAIR_RESOLUTIONS:
        if len(code) >= length:
            break
        lat_digit = int(lat // res)
        lng_digit = int(lng // res)
        lat -= lat_digit * res
        lng -= lng_digit * res
        code += _OLC_ALPHABET[lat_digit] + _OLC_ALPHABET[lng_digit]
    return code[:length]


def _olc_decode_center(full_code: str):
    digits = full_code.upper().replace('+', '')[:10]
    lat = lng = 0.0
    res = _OLC_PAIR_RESOLUTIONS[0]
    for i in range(0, len(digits), 2):
        res = _OLC_PAIR_RESOLUTIONS[i // 2]
        lat += _OLC_ALPHABET.index(digits[i]) * res
        lng += _OLC_ALPHABET.index(digits[i + 1]) * res
    return lat - 90.0 + res / 2, lng - 180.0 + res / 2


def recover_plus_code(short_code: str, ref_lat: float, ref_lng: float):
    """Coordenada (lng, lat) do centro de um Plus Code curto, perto da referência."""
    short_code = short_code.upper()
    padding = 8 - short_code.index('+')
    if padding <= 0:
        lat, lng = _olc_decode_center(short_code)
        return lng, lat
    resolution = 20.0 ** (2 - padding / 2)
    half = resolution / 2
    lat, lng = _olc_decode_center(_olc_prefix(ref_lat, ref_lng, padding) + short_code)
    if ref_lat + half < lat and lat - resolution >= -90:
        lat -= resolution
    elif ref_lat - half > lat and lat + resolution <= 90:
        lat += resolution
    if ref_lng + half < lng:
        lng -= resolution
    elif ref_lng - half > lng:
        lng += resolution
    return lng, lat


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', text).strip().lower()


def _split_plus_code(name: str):
    """('2Q4W+XF', 'natal, araguatins - to, brasil') ou (None, None)."""
    m = _PLUS_CODE_RE.match(name or '')
    if not m:
        return None, None
    locality = re.sub(r'\s*\[\d+:\w+\]\s*$', '', m.group(2))
    return m.group(1).upper(), _normalize(locality)


def _municipality(locality: str) -> str:
    """Município + UF da localidade de um Plus Code.

    'natal, araguatins - to, brasil' -> 'araguatins/to'
    'araguatins, to, brasil' -> 'araguatins/to'
    'pracas das mangueiras, nazare - to, 77895-000, brasil' -> 'nazare/to'
    """
    locality = re.sub(r',?\s*brasil$', '', locality)
    locality = re.sub(r',?\s*\d{5}-?\d{3}$', '', locality)  # CEP
    m = re.search(r'(?:^|,)\s*([^,]+?)\s*(?:-|,)\s*([a-z]{2})$', locality)
    if m:
        return f'{m.group(1).strip()}/{m.group(2)}'
    return locality.rsplit(',', 1)[-1].strip()


def _local(tag: str) -> str:
    """Nome da tag sem o namespace (`{http://...kml/2.2}Point` -> `Point`)."""
    return tag.rsplit('}', 1)[-1]


def _parse_coords(text: str) -> list:
    coords = []
    for chunk in (text or '').split():
        parts = chunk.split(',')
        if len(parts) >= 2:
            coords.append((float(parts[0]), float(parts[1])))
    return coords


def _read_kml_bytes(uploaded_file) -> bytes:
    raw = uploaded_file.read()
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith('.kml')]
            if not kml_names:
                raise KmzPointsError('O KMZ não contém nenhum arquivo .kml.')
            # O KML principal costuma ser o `doc.kml` na raiz.
            kml_names.sort(key=lambda n: (n.lower() != 'doc.kml', n.count('/')))
            return zf.read(kml_names[0])
    return raw


def _placemark_center(placemark):
    """Centro do Placemark: o `Point` se existir, senão o centroide do polígono."""
    ring = None
    for el in placemark.iter():
        tag = _local(el.tag)
        if tag not in ('Point', 'LinearRing'):
            continue
        for c in el.iter():
            if _local(c.tag) == 'coordinates':
                coords = _parse_coords(c.text)
                if tag == 'Point' and coords:
                    return coords[0]
                if tag == 'LinearRing' and len(coords) >= 4 and ring is None:
                    ring = coords
                break
    if ring:
        centroid = Polygon(ring).centroid
        return centroid.x, centroid.y
    return None


def parse_location_points(uploaded_file, first_index: int = 1, source: str = '') -> tuple:
    """Lê os Placemarks do arquivo. `first_index` permite numerar os pontos em
    sequência quando vários arquivos são enviados juntos."""
    try:
        root = ET.fromstring(_read_kml_bytes(uploaded_file))
    except ET.ParseError as e:
        raise KmzPointsError(f'Arquivo KML inválido: {e}')
    except zipfile.BadZipFile:
        raise KmzPointsError('Arquivo KMZ inválido ou corrompido.')

    # (nome, centro ou None) na ordem do arquivo.
    placemarks = []
    for placemark in root.iter():
        if _local(placemark.tag) != 'Placemark':
            continue
        name = ''
        for child in placemark:
            if _local(child.tag) == 'name':
                name = (child.text or '').strip()
                break
        placemarks.append((name, _placemark_center(placemark)))

    references = _plus_code_references(placemarks)

    points, skipped = [], []
    for name, center in placemarks:
        from_plus_code = False
        divergence_m = None
        if center is None:
            center = _center_from_plus_code(name, references)
            from_plus_code = center is not None
        else:
            from_code = _center_from_plus_code(name, references)
            if from_code is not None:
                divergence_m = _distance_m(center, from_code)
                if divergence_m > DIVERGENCE_LIMIT_M:
                    center = from_code
        if center is None:
            skipped.append(name or '(sem nome)')
            continue
        index = first_index + len(points)
        points.append(LocationPoint(
            index=index,
            name=name or f'Ponto {index}',
            lon=center[0],
            lat=center[1],
            source=source,
            from_plus_code=from_plus_code,
            divergence_m=divergence_m,
        ))

    if not points:
        raise KmzPointsError(f'Nenhum ponto ou polígono foi encontrado em {source or "o arquivo"}.')
    return points, skipped


def _distance_m(a, b) -> float:
    """Distância aproximada em metros entre dois (lng, lat) próximos."""
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110574
    return math.hypot(dx, dy)


def _median(values: list) -> float:
    values = sorted(values)
    return values[len(values) // 2]


def _plus_code_references(placemarks: list) -> dict:
    """Centro (mediana) dos pontos com coordenada, por município e por localidade.

    Mediana em vez de média porque alguns pontos do próprio arquivo vêm
    geocodificados em outro estado (ex.: "Nazaré - TO" caindo na Bahia) e
    puxariam a referência para longe.
    """
    groups = {}
    for name, center in placemarks:
        if center is None:
            continue
        _, locality = _split_plus_code(name)
        if not locality:
            continue
        for key in (('loc', locality), ('mun', _municipality(locality))):
            groups.setdefault(key, []).append(center)
    return {
        key: (_median([c[1] for c in centers]), _median([c[0] for c in centers]))
        for key, centers in groups.items()
    }


def _center_from_plus_code(name: str, references: dict):
    code, locality = _split_plus_code(name)
    if not code:
        return None
    if code.index('+') >= 8:
        return recover_plus_code(code, 0.0, 0.0)
    ref = references.get(('mun', _municipality(locality))) or references.get(('loc', locality))
    if ref is None:
        return None
    return recover_plus_code(code, ref[0], ref[1])


def locate_cars(points: list) -> list:
    """Preenche `point.cars` com os imóveis do SICAR que contêm o ponto central.

    Uma única consulta para todos os pontos (podem ser milhares), usando o
    índice espacial de `geometria_util`. Um ponto pode cair em mais de um CAR
    quando os imóveis declarados se sobrepõem.
    """
    if not points:
        return points

    sql = """
        SELECT p.idx, s.numero_car, s.status, s.area_ha
        FROM unnest(%s::int[], %s::float8[], %s::float8[]) AS p(idx, lon, lat)
        JOIN tb_registro_sicar s
          ON ST_Intersects(s.geometria_util, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4674))
        ORDER BY p.idx, s.area_ha DESC NULLS LAST
    """
    by_index = {p.index: p for p in points}
    with connection.cursor() as cursor:
        cursor.execute(sql, [
            [p.index for p in points],
            [p.lon for p in points],
            [p.lat for p in points],
        ])
        for idx, car_number, status, area_ha in cursor.fetchall():
            by_index[idx].cars.append({
                'car_number': car_number,
                'status': status or '',
                'area_ha': area_ha,
            })
    return points


def summarize_cars(points: list) -> list:
    """CARs distintos encontrados (cada um conta uma vez), com os pontos que
    caíram em cada um."""
    cars = {}
    for p in points:
        for car in p.cars:
            entry = cars.setdefault(car['car_number'], {**car, 'points': []})
            entry['points'].append(p)
    return sorted(cars.values(), key=lambda c: (-len(c['points']), c['car_number']))


def car_perimeters(car_numbers: list) -> dict:
    """GeoJSON do perímetro de cada CAR, para desenhar no mapa.

    Simplificado em ~2 m (0.00002°) para a página não ficar pesada quando o
    arquivo encontra centenas de imóveis; o desenho não muda visivelmente.
    """
    if not car_numbers:
        return {}
    sql = """
        SELECT numero_car, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometria_util, 0.00002), 6)
        FROM tb_registro_sicar
        WHERE numero_car = ANY(%s) AND geometria_util IS NOT NULL
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [list(car_numbers)])
        return {car: json.loads(geojson) for car, geojson in cursor.fetchall() if geojson}


def car_details(car_numbers: list) -> dict:
    """Dados extras de cada CAR para a ficha da tela: data da última
    atualização no SICAR e a hidrografia declarada (por tipo, com área)."""
    if not car_numbers:
        return {}
    car_numbers = list(car_numbers)
    details = {car: {'last_update': None, 'hydrography': []} for car in car_numbers}
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT numero_car, ultima_atualizacao FROM tb_registro_sicar WHERE numero_car = ANY(%s)',
            [car_numbers],
        )
        for car, last_update in cursor.fetchall():
            details[car]['last_update'] = last_update
        cursor.execute("""
            SELECT cod_imovel, nom_tema, COUNT(*), SUM(area_ha)
            FROM tb_hidrografia_declarada
            WHERE cod_imovel = ANY(%s)
            GROUP BY 1, 2
            ORDER BY 1, 4 DESC NULLS LAST
        """, [car_numbers])
        for car, theme, count, area_ha in cursor.fetchall():
            if car in details:
                details[car]['hydrography'].append({'theme': theme, 'count': count, 'area_ha': area_ha})
    return details
