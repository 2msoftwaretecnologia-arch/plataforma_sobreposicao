"""Polígono enviado para recortar o download de imagem (aba Imagem do mapa).

Aceita shapefile em ZIP, KML/KMZ e GeoJSON e devolve uma geometria só, em
lon/lat (EPSG:4326), com todos os polígonos do arquivo. O navegador usa essa
geometria para escolher o retângulo da imagem e recortar o que fica fora
(ver download_area.js e image_export.js).
"""
import io
import json
import os
import zipfile

import geopandas as gpd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from analysis.services.view_services.kml_upload_service import KmlUploadError, KmlUploadService
from analysis.services.view_services.zip_upload_service import ZipUploadService

MAX_BYTES = 30 * 1024 * 1024
# Acima disso a geometria é simplificada: o recorte é no pixel da imagem
# (≥ 0,3 m), e milhares de vértices a mais só pesam no navegador.
MAX_VERTICES = 20000
EXTENSIONS = ('.zip', '.kml', '.kmz', '.geojson', '.json')


class DownloadAreaError(ValueError):
    pass


def read_download_area(uploaded_file) -> dict:
    """`{'geometry': GeoJSON, 'nome': nome do arquivo sem extensão}`."""
    name = uploaded_file.name or ''
    lower = name.lower()
    if not lower.endswith(EXTENSIONS):
        raise DownloadAreaError('Envie um shapefile em ZIP, um KML/KMZ ou um GeoJSON.')
    if uploaded_file.size and uploaded_file.size > MAX_BYTES:
        raise DownloadAreaError(f'O arquivo passa de {MAX_BYTES // (1024 * 1024)} MB.')

    if lower.endswith('.zip'):
        gdf = _read_zip(uploaded_file)
    elif lower.endswith(('.kml', '.kmz')):
        try:
            gdf = KmlUploadService().extract_geodataframe(uploaded_file)
        except KmlUploadError as e:
            raise DownloadAreaError(str(e))
    else:
        gdf = _read_geojson(uploaded_file)

    if gdf is None or gdf.empty:
        raise DownloadAreaError('O arquivo não tem nenhum polígono (só pontos ou linhas não formam uma área).')
    gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(['Polygon', 'MultiPolygon'])]
    if gdf.empty:
        raise DownloadAreaError('O arquivo não tem nenhum polígono (só pontos ou linhas não formam uma área).')

    if gdf.crs is None:
        # GeoJSON, ou shapefile sem .prj: só dá para seguir se as
        # coordenadas já são graus.
        if not _looks_like_degrees(gdf.total_bounds):
            raise DownloadAreaError(
                'O shapefile não tem o arquivo .prj com o sistema de coordenadas. Inclua o .prj no ZIP.'
                if lower.endswith('.zip') else
                'O GeoJSON precisa estar em graus (longitude/latitude, WGS84 ou SIRGAS 2000).')
        gdf = gdf.set_crs('EPSG:4326')
    gdf = gdf.to_crs('EPSG:4326')

    geometry = unary_union([g if g.is_valid else g.buffer(0) for g in gdf.geometry])
    if geometry.is_empty or geometry.geom_type not in ('Polygon', 'MultiPolygon'):
        raise DownloadAreaError('Não foi possível montar uma área com os polígonos do arquivo.')
    if not _looks_like_degrees(geometry.bounds):
        raise DownloadAreaError('As coordenadas do arquivo estão fora do globo: confira o sistema de coordenadas.')

    tolerance = 0.00001  # ~1 m
    while _vertex_count(geometry) > MAX_VERTICES and tolerance < 0.01:
        geometry = geometry.simplify(tolerance, preserve_topology=True)
        tolerance *= 3

    return {'geometry': mapping(geometry), 'nome': os.path.splitext(os.path.basename(name))[0]}


def _read_zip(uploaded_file):
    try:
        gdf = ZipUploadService().extract_geodataframe(uploaded_file)
    except zipfile.BadZipFile:
        raise DownloadAreaError('Arquivo ZIP inválido ou corrompido.')
    if gdf is None:
        raise DownloadAreaError('O ZIP não tem nenhum shapefile com polígonos (.shp, .shx, .dbf e .prj).')
    return gdf


def _read_geojson(uploaded_file):
    try:
        data = json.load(io.TextIOWrapper(uploaded_file, encoding='utf-8-sig'))
    except (ValueError, UnicodeDecodeError) as e:
        raise DownloadAreaError(f'GeoJSON inválido: {e}')

    geometries = []

    def walk(g):
        if not isinstance(g, dict):
            return
        kind = g.get('type')
        if kind == 'FeatureCollection':
            for f in g.get('features') or []:
                walk(f)
        elif kind == 'Feature':
            walk(g.get('geometry'))
        elif kind == 'GeometryCollection':
            for item in g.get('geometries') or []:
                walk(item)
        elif kind in ('Polygon', 'MultiPolygon'):
            try:
                geometries.append(shape(g))
            except (ValueError, TypeError, IndexError):
                pass

    walk(data)
    if not geometries:
        return None
    # GeoJSON é sempre lon/lat (RFC 7946); o `crs` antigo, se vier, é ignorado.
    return gpd.GeoDataFrame(geometry=geometries, crs=None)


def _looks_like_degrees(bounds) -> bool:
    minx, miny, maxx, maxy = bounds
    return -180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90


def _vertex_count(geometry) -> int:
    polygons = geometry.geoms if geometry.geom_type == 'MultiPolygon' else [geometry]
    return sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors) for p in polygons)
