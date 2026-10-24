"""Exporta, em SHP (zip) ou KML, os polígonos de uma base que caíram na
propriedade analisada — o recorte que aparece no resultado, com as colunas
de cada item."""
import io
import os
import re
import tempfile
import zipfile

import geopandas as gpd
from django.utils.text import slugify
from shapely import wkt as shapely_wkt
from shapely.ops import unary_union

# Chaves do resultado que não são colunas do item (geometria e cor do mapa).
SKIPPED_KEYS = {'polygon_wkt', 'polygon_geojson', 'color', 'mapbiomas_url'}

# Shapefile só aceita um tipo de geometria por arquivo.
GEOMETRY_FAMILIES = (
    ('Polygon', ''),
    ('LineString', '_linhas'),
    ('Point', '_pontos'),
)


class BaseExportError(Exception):
    pass


def find_base(resultado, nome_base):
    for base in (resultado or {}).get('resultados_por_base') or []:
        if base.get('nome_base') == nome_base:
            return base
    return None


def export_filename(nome_base, car_value=''):
    name = slugify(re.sub(r'^Base (de Dados )?(d[aeo]s? )?', '', nome_base)) or 'base'
    return f'{name}_{slugify(car_value)}' if car_value else name


def _column_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _parts(geom):
    """Recortes podem virar GeometryCollection (polígono + linha na borda):
    separa em uma geometria por família."""
    if geom.geom_type != 'GeometryCollection':
        return [geom]
    parts = []
    for family, _ in GEOMETRY_FAMILIES:
        pieces = [g for g in geom.geoms if family in g.geom_type]
        if pieces:
            parts.append(unary_union(pieces))
    return parts


def base_geodataframe(base):
    rows, geometries = [], []
    for record in base.get('areas_encontradas') or []:
        wkt = record.get('polygon_wkt')
        if not wkt:
            continue
        try:
            geom = shapely_wkt.loads(wkt)
        except Exception:
            continue
        attrs = {k: _column_value(v) for k, v in record.items() if k not in SKIPPED_KEYS}
        for part in _parts(geom):
            if part.is_empty:
                continue
            rows.append(attrs)
            geometries.append(part)
    if not rows:
        raise BaseExportError('Esta base não tem polígonos na propriedade para exportar.')
    return gpd.GeoDataFrame(rows, geometry=geometries, crs='EPSG:4674')


def property_geodataframe(alvo_wkt, car='', status_car=''):
    """O contorno da área analisada, com o CAR e a situação dele."""
    if not alvo_wkt:
        raise BaseExportError('Nenhuma geometria da propriedade foi encontrada para exportação.')
    try:
        geom = shapely_wkt.loads(alvo_wkt)
    except Exception:
        raise BaseExportError('Geometria da propriedade inválida.')
    return gpd.GeoDataFrame([{'car': car, 'status_car': status_car}], geometry=[geom], crs='EPSG:4674')


def to_shapefile_zip(gdf, name):
    with tempfile.TemporaryDirectory() as tmpdir:
        for family, suffix in GEOMETRY_FAMILIES:
            subset = gdf[gdf.geometry.geom_type.str.contains(family)]
            if not subset.empty:
                subset.to_file(os.path.join(tmpdir, f'{name}{suffix}.shp'),
                               driver='ESRI Shapefile', encoding='utf-8', index=False)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, filename), filename)
    return buffer.getvalue()


def to_kml(gdf, name):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, f'{name}.kml')
        gdf.to_file(path, driver='KML')
        with open(path, 'rb') as f:
            return f.read()
