import geopandas as gpd

def extrair_cordenadas(arquivo_shp = "exports/Area_do_Imovel.shp"):
    """
    Lê um shapefile e retorna o primeiro polígono no formato POLYGON ((...))
    """
    
    if arquivo_shp is None:
        print("Erro: Arquivo shapefile não fornecido")
        return None
        
    try:
        # Ler o shapefile
        gdf = gpd.read_file(arquivo_shp)
        
        # Verificar se há geometrias no arquivo
        if gdf.empty or gdf.geometry.empty:
            print("Erro: Arquivo shapefile está vazio ou não contém geometrias")
            return None
        
        # Para cada geometria no arquivo
        for geom in gdf.geometry:
            if geom is None:
                continue
                
            if geom.geom_type == 'Polygon':
                # Extrai as coordenadas do exterior do polígono
                coords = list(geom.exterior.coords)
                # Formata no estilo POLYGON ((x1 y1, x2 y2, ...))
                coord_str = ", ".join([f"{x} {y}" for x, y in coords])
                return f"POLYGON (({coord_str}))"
                
            elif geom.geom_type == 'MultiPolygon':
                # Para multipolígonos, retorna o primeiro polígono
                if len(geom.geoms) > 0:
                    primeira_parte = geom.geoms[0]
                    coords = list(primeira_parte.exterior.coords)
                    coord_str = ", ".join([f"{x} {y}" for x, y in coords])
                    return f"POLYGON (({coord_str}))"
        
        print("Erro: Nenhuma geometria válida encontrada no arquivo")
        return None
                    
    except Exception as e:
        print(f"Erro ao ler o arquivo: {e}")
        return None

