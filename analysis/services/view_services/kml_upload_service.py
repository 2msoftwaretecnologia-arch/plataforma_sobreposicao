"""Área do imóvel enviada como KML ou KMZ (Google Earth, SIGEF, SICAR...).

Todos os polígonos do arquivo viram uma geometria só: um imóvel desenhado em
várias glebas chega como vários Placemarks. Pontos e linhas são ignorados.
"""
import zipfile
from typing import Optional
from xml.etree import ElementTree as ET

import geopandas as gpd
from shapely.geometry import Polygon
from shapely.ops import unary_union

from analysis.services.view_services.kmz_points_service import (
    KmzPointsError,
    _local,
    _parse_coords,
    _read_kml_bytes,
)


class KmlUploadError(ValueError):
    pass


class KmlUploadService:

    def extract_geodataframe(self, uploaded_file) -> Optional[gpd.GeoDataFrame]:
        """GeoDataFrame (EPSG:4326, o datum do KML) com a união dos polígonos,
        ou `None` quando o arquivo não tem nenhum polígono."""
        try:
            root = ET.fromstring(_read_kml_bytes(uploaded_file))
        except KmzPointsError as e:
            raise KmlUploadError(str(e))
        except ET.ParseError as e:
            raise KmlUploadError(f'Arquivo KML inválido: {e}')
        except zipfile.BadZipFile:
            raise KmlUploadError('Arquivo KMZ inválido ou corrompido.')

        polygons = [p for p in (self._polygon(el) for el in root.iter() if _local(el.tag) == 'Polygon') if p]
        if not polygons:
            return None

        geometry = unary_union(polygons)
        return gpd.GeoDataFrame(geometry=[geometry], crs='EPSG:4326')

    def _polygon(self, element) -> Optional[Polygon]:
        shell, holes = None, []
        for boundary in element:
            kind = _local(boundary.tag)
            if kind not in ('outerBoundaryIs', 'innerBoundaryIs'):
                continue
            coords = next((_parse_coords(c.text) for c in boundary.iter() if _local(c.tag) == 'coordinates'), [])
            if len(coords) < 3:
                continue
            if kind == 'outerBoundaryIs':
                shell = coords
            else:
                holes.append(coords)
        if not shell:
            return None
        polygon = Polygon(shell, holes)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        return polygon if not polygon.is_empty else None
