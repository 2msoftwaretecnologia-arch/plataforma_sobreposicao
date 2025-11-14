from typing import Optional
import geopandas as gpd


class ZipUploadService:
    
    def extract_geodataframe(self, zip_file_path) -> Optional[gpd.GeoDataFrame]:
        """Extrai um GeoDataFrame de um arquivo ZIP enviado."""
        try:
            gdf = gpd.read_file(zip_file_path)
            return gdf
        except Exception as e:
            print(f"Erro ao ler o arquivo ZIP: {e}")
            return None