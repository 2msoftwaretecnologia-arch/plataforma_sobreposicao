import json

from django.contrib.gis.geos import GEOSGeometry

# Só para o desenho no mapa: ~1 m de tolerância e 6 casas decimais (~10 cm).
# Recortes de MapBiomas/PRODES chegam com milhares de vértices em "escadinha"
# de pixel e 15 casas, o que travava a abertura do mapa.
MAP_SIMPLIFY_TOLERANCE = 0.00001
MAP_COORD_DECIMALS = 6


def _round_coords(coords):
    if isinstance(coords, (int, float)):
        return round(coords, MAP_COORD_DECIMALS)
    return [_round_coords(c) for c in coords]


def _light_geojson(gj):
    """GeoJSON simplificado para o mapa; devolve o original se não der."""
    if not gj:
        return gj
    try:
        geom = GEOSGeometry(gj if isinstance(gj, str) else json.dumps(gj))
        simple = geom.simplify(MAP_SIMPLIFY_TOLERANCE, preserve_topology=True)
        if simple.empty:
            simple = geom
        data = json.loads(simple.json)
    except Exception:
        return gj
    if 'coordinates' in data:
        data['coordinates'] = _round_coords(data['coordinates'])
    elif 'geometries' in data:
        for g in data['geometries']:
            g['coordinates'] = _round_coords(g.get('coordinates', []))
    return data


def format_data_map(data):
    """Monta `data['map_items']` a partir de `data['resultado']`, no formato
    esperado pelo template `analysis/results.html` / `maps.js`."""
    resultado = data.get('resultado') or {}
    alvo_geojson = resultado.get('alvo_geojson')
    tamanho_area = resultado.get('tamanho_area', 0)
    poligonos_imoveis = resultado.get('poligonos_imoveis', [])

    if not alvo_geojson:
        return data

    items = [
        {
            "gj": _light_geojson(alvo_geojson),
            "label": "Área da Propriedade",
            "area": f'{tamanho_area:.4f} ha',
            "color": "#000000",
            "fonte": "Área da Propriedade",
        }
    ]

    for p in poligonos_imoveis:
        items.append({
            "gj": _light_geojson(p["polygon_geojson"]),
            "label": p["item_info"],
            "area": f'{p["area"]:.4f} ha',
            "color": p["color"],
            "fonte": p["fonte"],
        })

    data['map_items'] = items
    return data
