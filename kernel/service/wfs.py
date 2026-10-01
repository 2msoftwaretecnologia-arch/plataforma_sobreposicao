import geopandas as gpd
import pandas as pd
import requests

SRID = 4674
PAGE_SIZE = 5000
TIMEOUT = 300


def fetch_wfs(url, type_name, cql_filter=None, properties=None, sort_by=None):
    """Baixa uma camada de um GeoServer via WFS 2.0 (GeoJSON), em páginas, já
    em SIRGAS 2000. Usado pelas bases que vêm de API em vez de shapefile
    (PRODES do INPE, Zoneamento do Geoportal SEPLAN-TO).

    `sort_by` deixa a paginação estável (o GeoServer exige ordenação para
    paginar sem repetir/pular feições)."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": "application/json",
        "srsName": f"EPSG:{SRID}",
        "count": PAGE_SIZE,
    }
    if cql_filter:
        params["CQL_FILTER"] = cql_filter
    if properties:
        params["propertyName"] = properties
    if sort_by:
        params["sortBy"] = sort_by

    session = requests.Session()
    frames, start = [], 0
    while True:
        response = session.get(url, params={**params, "startIndex": start}, timeout=TIMEOUT)
        response.raise_for_status()
        features = response.json().get("features", [])
        if not features:
            break
        # GeoJSON é sempre longitude/latitude, na projeção pedida em srsName.
        frames.append(gpd.GeoDataFrame.from_features(features, crs=f"EPSG:{SRID}"))
        if len(features) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    if not frames:
        raise ValueError(f"A API não retornou dados da camada {type_name}.")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=f"EPSG:{SRID}")
