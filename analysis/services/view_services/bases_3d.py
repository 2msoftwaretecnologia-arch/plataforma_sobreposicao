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

# Bases cujo tour tem uma parada por valor de uma coluna (em vez de uma só):
# modelo -> (coluna no banco, rótulos dos valores).
TOUR_GROUPS = {
    'SicarRecord': ('status', {'AT': 'Ativo', 'PE': 'Pendente', 'SU': 'Suspenso', 'CA': 'Cancelado'}),
}

SUMMARY_CACHE_KEY = 'bases_3d:summary:v2'
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
        'stops': _tour_stops(cursor, base, count),
        'props': [{'key': p['key'], 'label': p['label']} for p in base['props']],
    }


def _tour_stops(cursor, base, count):
    """Paradas do tour: a maior feição inteiramente dentro do estado — uma
    por grupo quando a base está em `TOUR_GROUPS`, senão uma só."""
    q = connection.ops.quote_name
    group = TOUR_GROUPS.get(base['modelo'])
    group_expr = f"UPPER(s.{q(group[0])})" if group else "''"
    cursor.execute(f"""
        WITH {_TO_CTE},
        inside AS (
            SELECT {group_expr} AS grp, s.geometria_util AS geom, COALESCE(s.area_ha, 0) AS area
            FROM {q(base['table'])} s, tocantins t
            WHERE s.geometria_util @ t.geom AND ST_Within(s.geometria_util, t.geom)
        ),
        largest AS (
            SELECT DISTINCT ON (grp) grp, ST_PointOnSurface(geom) AS p
            FROM inside ORDER BY grp, area DESC
        )
        SELECT l.grp, ST_X(l.p), ST_Y(l.p), c.n
        FROM largest l
        JOIN (SELECT grp, COUNT(*) AS n FROM inside GROUP BY grp) c USING (grp)
        ORDER BY c.n DESC
    """, {'to': tocantins_wkt()})
    rows = cursor.fetchall()
    if not group:
        return [{'value': None, 'label': None, 'focus': [x, y], 'count': count} for _, x, y, _n in rows]
    labels = group[1]
    return [{'value': grp, 'label': labels.get(grp, grp or 'Sem situação'), 'focus': [x, y], 'count': n}
            for grp, x, y, n in rows]


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
    if not base or not summary or z < summary['min_zoom']:
        return None
    if not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        return None

    q = connection.ops.quote_name
    extra = ''.join(f", s.{q(p['column'])}::text AS {p['key']}" for p in base['props'])
    sql = f"""
        WITH {_TO_CTE},
        bounds AS (
            SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS geom_3857,
                   ST_Transform(ST_TileEnvelope(%(z)s, %(x)s, %(y)s), 4674) AS geom_4674
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
              AND s.geometria_util && t.geom
              AND ST_Intersects(s.geometria_util, t.geom)
        )
        SELECT ST_AsMVT(mvt, 'layer', 4096, 'geom', 'fid') FROM mvt WHERE geom IS NOT NULL
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, {'to': tocantins_wkt(), 'z': z, 'x': x, 'y': y})
        tile = cursor.fetchone()[0]
    return bytes(tile) if tile else None
