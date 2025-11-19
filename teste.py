import geopandas as gpd

df = gpd.read_file(r"C:\Users\Pessoa\Downloads\AREA_IMOVEL.zip")
print(df.crs)

df_en = gpd.read_file(r"C:\Users\Pessoa\Downloads\other\shp\apas\Apas.shp")
print(df_en.crs)