"""
Dados do mapa 3D das bases (página `bases_3d`): catálogo das camadas que têm
dados no Tocantins e geração dos vector tiles (MVT) direto no PostGIS.

Tudo é recortado pelo contorno do Tocantins (IBGE, em
`analysis/static/analysis/data/tocantins.geojson`) — a plataforma só analisa
imóveis do estado, e algumas bases importadas trazem feições de fora dele.
"""

import json
from functools import lru_cache
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry
from django.core.cache import cache
from django.db import connection

from control_panel.bases_config import BASES_CONFIG
from control_panel.layer_registry import LAYER_REGISTRY

TOCANTINS_GEOJSON = Path(__file__).resolve().parents[2] / 'static' / 'analysis' / 'data' / 'tocantins.geojson'

# Acima deste número de feições um tile em zoom baixo cobriria dezenas de
# milhares de polígonos; essas bases só aparecem a partir de `DENSE_MIN_ZOOM`.
DENSE_THRESHOLD = 5000
DENSE_MIN_ZOOM = 9
SPARSE_MIN_ZOOM = 5

# Colunas extraídas levadas para o tile (popup). Limitado para manter o tile
# leve e para não expor dados pessoais (ex.: CPF/CNPJ dos embargos).
MAX_PROPS = 2

# Bases exibidas no mapa 3D. Por enquanto só o perímetro dos imóveis do
# SICAR; para incluir outra camada basta acrescentar o `modelo` aqui.
BASES_3D = ('SicarRecord',)

# Nível máximo de tile gerado. Acima disso o mapa amplia os tiles do nível
# 11 (4096 unidades por ~20 km, ~4,8 m de precisão — menos de um pixel no
# zoom do tour) em vez de pedir novos: trocar de nível enquanto a câmera
# desce sobre uma cidade fazia as linhas pontilhadas "pularem".
MAX_TILE_ZOOM = 11

# Tiles prontos ficam em cache: gerar um tile custa ~0,5–1 s no PostGIS e,
# enquanto ele não chega, o mapa mostra a versão de outro nível (piscando).
TILE_CACHE_SECONDS = 60 * 60 * 6

# Propriedades extras por base nos tiles. No SICAR, o código IBGE do
# município (vem dentro do número do CAR: UF-<7 dígitos>-<hash>), usado pelo
# tour para mostrar só os imóveis da cidade da vez.
TILE_EXTRA_SQL = {
    'SicarRecord': "SUBSTRING(s.numero_car FROM 4 FOR 7) AS mun",
}

SUMMARY_CACHE_KEY = 'bases_3d:summary:v3'

# Tour de cidade em cidade: sedes dos 139 municípios do Tocantins (IBGE,
# coordenadas do projeto kelvins/municipios-brasileiros).
MUNICIPIOS_JSON = TOCANTINS_GEOJSON.with_name('tocantins_municipios.json')
CITIES_CACHE_KEY = 'bases_3d:cities:v2'

# Onde o tour para em cada município: não na sede (área urbana, quase sem
# CAR), mas no trecho de ~5 km com mais imóveis do CAR daquele município.
FOCUS_CELL_DEG = 0.05
SUMMARY_CACHE_SECONDS = 60 * 60

_GEOM_KIND = {'POLYGON': 'polygon', 'MULTIPOLYGON': 'polygon',
              'LINESTRING': 'line', 'MULTILINESTRING': 'line',
              'POINT': 'point', 'MULTIPOINT': 'point'}
_EXTRACT_TYPE = {'point': 1, 'line': 2, 'polygon': 3}


@lru_cache(maxsize=1)
def tocantins_wkt():
    data = json.loads(TOCANTINS_GEOJSON.read_text(encoding='utf-8'))
    # IBGE publica em SIRGAS 2000; o SRID vai no ST_GeomFromText (4674).
    geom = GEOSGeometry(json.dumps(data['features'][0]['geometry']))
    return geom.wkt


_ACRONYMS = {'Sicar': 'SICAR', 'Sigef': 'SIGEF', 'Prodes': 'PRODES'}


def _short_name(nome_base):
    for prefix in ('Base de Dados de ', 'Base de Dados ', 'Base de '):
        if nome_base.startswith(prefix):
            nome_base = nome_base[len(prefix):]
            break
    return _ACRONYMS.get(nome_base, nome_base)


@lru_cache(maxsize=1)
def catalog():
    """Bases conhecidas, indexadas por `modelo`, com tabela e colunas já
    resolvidas a partir do Model (os nomes vêm do código, nunca do request)."""
    bases = {}
    for cfg in BASES_CONFIG:
        if cfg['modelo'] not in BASES_3D:
            continue
        entry = LAYER_REGISTRY.get(cfg['modelo'])
        if not entry:
            continue
        model = entry['model']
        props = []
        for col in cfg.get('colunas_extraidas', []):
            if 'cpf' in col['campo'].lower():
                continue
            try:
                field = model._meta.get_field(col['campo'])
            except Exception:
                continue
            props.append({'key': f'p{len(props)}', 'column': field.column, 'label': col['rotulo']})
            if len(props) == MAX_PROPS:
                break
        bases[cfg['modelo']] = {
            'modelo': cfg['modelo'],
            'nome': _short_name(cfg['nome_base']),
            'cor': cfg.get('cor') or '#3a7a4b',
            'table': model._meta.db_table,
            'pk': model._meta.pk.column,
            'props': props,
        }
    return bases


_TO_CTE = "tocantins AS (SELECT ST_GeomFromText(%(to)s, 4674) AS geom)"


def _base_summary(cursor, base):
    q = connection.ops.quote_name
    table = q(base['table'])
    cursor.execute(f"""
        WITH {_TO_CTE}
        SELECT COUNT(*), MIN(GeometryType(s.geometria_util))
        FROM {table} s, tocantins t
        WHERE s.geometria_util && t.geom AND ST_Intersects(s.geometria_util, t.geom)
    """, {'to': tocantins_wkt()})
    count, geom_type = cursor.fetchone()
    if not count:
        return None

    kind = _GEOM_KIND.get((geom_type or '').upper(), 'polygon')
    return {
        'modelo': base['modelo'],
        'nome': base['nome'],
        'cor': base['cor'],
        'kind': kind,
        'count': count,
        'min_zoom': DENSE_MIN_ZOOM if count > DENSE_THRESHOLD else SPARSE_MIN_ZOOM,
        'props': [{'key': p['key'], 'label': p['label']} for p in base['props']],
    }


def bases_summary():
    """Bases com dados no Tocantins, na ordem do catálogo. Em cache porque
    contar/achar o ponto de parada varre a tabela inteira."""
    summary = cache.get(SUMMARY_CACHE_KEY)
    if summary is not None:
        return summary
    summary = []
    with connection.cursor() as cursor:
        for base in catalog().values():
            item = _base_summary(cursor, base)
            if item:
                summary.append(item)
    cache.set(SUMMARY_CACHE_KEY, summary, SUMMARY_CACHE_SECONDS)
    return summary


def render_tile(modelo, z, x, y):
    """MVT da base `modelo` para o tile z/x/y, ou None se vazio/desconhecido."""
    base = catalog().get(modelo)
    summary = next((b for b in bases_summary() if b['modelo'] == modelo), None)
    if not base or not summary or not (summary['min_zoom'] <= z <= MAX_TILE_ZOOM):
        return None
    if not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        return None

    # A contagem entra na chave para uma reimportação da base não servir
    # tiles antigos (o resumo, com a contagem, é refeito a cada hora).
    cache_key = f"bases_3d:tile:v2:{modelo}:{summary['count']}:{z}:{x}:{y}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None
    tile = _query_tile(base, summary, z, x, y)
    cache.set(cache_key, tile or b'', TILE_CACHE_SECONDS)
    return tile


def _query_tile(base, summary, z, x, y):
    q = connection.ops.quote_name
    extra = ''.join(f", s.{q(p['column'])}::text AS {p['key']}" for p in base['props'])
    if base['modelo'] in TILE_EXTRA_SQL:
        extra += ', ' + TILE_EXTRA_SQL[base['modelo']]
    sql = f"""
        WITH {_TO_CTE},
        bounds AS (
            SELECT e.geom_3857, e.geom_4674, ST_Within(e.geom_4674, t.geom) AS inside
            FROM tocantins t, LATERAL (
                SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS geom_3857,
                       ST_Transform(ST_TileEnvelope(%(z)s, %(x)s, %(y)s), 4674) AS geom_4674
            ) e
        ),
        mvt AS (
            SELECT ST_AsMVTGeom(
                       ST_Transform(ST_CollectionExtract(s.geometria_util, {_EXTRACT_TYPE[summary['kind']]}), 3857),
                       b.geom_3857, 4096, 64, true
                   ) AS geom,
                   s.{q(base['pk'])} AS fid,
                   COALESCE(s.area_ha, 0) AS area_ha
                   {extra}
            FROM {q(base['table'])} s, bounds b, tocantins t
            WHERE s.geometria_util && b.geom_4674
              AND (b.inside OR (s.geometria_util && t.geom AND ST_Intersects(s.geometria_util, t.geom)))
        )
        SELECT ST_AsMVT(mvt, 'layer', 4096, 'geom', 'fid') FROM mvt WHERE geom IS NOT NULL
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, {'to': tocantins_wkt(), 'z': z, 'x': x, 'y': y})
        tile = cursor.fetchone()[0]
    return bytes(tile) if tile else None


def cities_summary():
    """Municípios com o número de imóveis do CAR e o ponto de parada do tour
    (`focus`: centro dos imóveis na célula da grade com mais imóveis).

    O código IBGE do município está no próprio número do CAR
    (UF-<7 dígitos>-<hash>), então não é preciso cruzar geometrias."""
    cities = cache.get(CITIES_CACHE_KEY)
    if cities is not None:
        return cities
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT SUBSTRING(numero_car FROM 4 FOR 7), COUNT(*)
            FROM tb_registro_sicar
            GROUP BY 1
        """)
        cars = dict(cursor.fetchall())
        cursor.execute("""
            WITH p AS (
                SELECT SUBSTRING(numero_car FROM 4 FOR 7) AS mun,
                       ST_PointOnSurface(geometria_util) AS g
                FROM tb_registro_sicar
                WHERE geometria_util IS NOT NULL
            ),
            cells AS (
                SELECT mun, COUNT(*) AS n, AVG(ST_X(g)) AS x, AVG(ST_Y(g)) AS y
                FROM p
                GROUP BY mun, FLOOR(ST_X(g) / %(cell)s), FLOOR(ST_Y(g) / %(cell)s)
            )
            SELECT DISTINCT ON (mun) mun, x, y FROM cells ORDER BY mun, n DESC
        """, {'cell': FOCUS_CELL_DEG})
        focus = {mun: [x, y] for mun, x, y in cursor.fetchall()}
    cities = [
        dict(city, cars=cars.get(city['codigo'], 0),
             focus=focus.get(city['codigo'], [city['lon'], city['lat']]))
        for city in json.loads(MUNICIPIOS_JSON.read_text(encoding='utf-8'))
    ]
    cache.set(CITIES_CACHE_KEY, cities, SUMMARY_CACHE_SECONDS)
    return cities
