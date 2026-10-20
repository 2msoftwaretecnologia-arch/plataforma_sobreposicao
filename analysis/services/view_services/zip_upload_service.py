import os
import tempfile
import zipfile
from typing import Optional

import geopandas as gpd


class ZipUploadService:

    # Camada do imóvel no shapefile baixado do SICAR, que vem com várias
    # camadas (APP, reserva legal...) em zips dentro do zip.
    PREFERRED_LAYER = 'AREA_IMOVEL'
    MAX_NESTING = 3

    def extract_geodataframe(self, zip_file) -> Optional[gpd.GeoDataFrame]:
        """Extrai um GeoDataFrame de um arquivo ZIP enviado.

        O .shp pode estar na raiz, dentro de pastas ou em zips aninhados;
        quando há mais de um, prefere a camada do imóvel e depois a primeira
        com polígonos.
        """
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                zip_path = os.path.join(tmp_dir, 'upload.zip')
                with open(zip_path, 'wb') as out:
                    if hasattr(zip_file, 'chunks'):
                        for chunk in zip_file.chunks():
                            out.write(chunk)
                    else:
                        with open(zip_file, 'rb') as src:
                            out.write(src.read())

                shapefiles = self._find_shapefiles(zip_path, tmp_dir, 0)
                shapefiles.sort(key=lambda p: self.PREFERRED_LAYER not in os.path.basename(p).upper())

                for vsi_path in shapefiles:
                    gdf = gpd.read_file(vsi_path)
                    if gdf.empty:
                        continue
                    if gdf.geom_type.isin(['Polygon', 'MultiPolygon']).any():
                        return gdf
                return None
        except zipfile.BadZipFile:
            raise
        except Exception as e:
            print(f"Erro ao ler o arquivo ZIP: {e}")
            return None

    def _find_shapefiles(self, zip_path, tmp_dir, depth):
        """Caminhos /vsizip/ de todos os .shp do zip, abrindo zips internos."""
        found = []
        with zipfile.ZipFile(zip_path) as zf:
            for index, name in enumerate(zf.namelist()):
                lower = name.lower()
                if '__macosx' in lower:
                    continue
                if lower.endswith('.shp'):
                    found.append(f'/vsizip/{zip_path}/{name}')
                elif lower.endswith('.zip') and depth < self.MAX_NESTING:
                    inner_path = os.path.join(tmp_dir, f'inner_{depth}_{index}.zip')
                    with open(inner_path, 'wb') as out:
                        out.write(zf.read(name))
                    found.extend(self._find_shapefiles(inner_path, tmp_dir, depth + 1))
        return found
