from django.conf import settings


def planet_tiles_url():
    try:
        mosaic = getattr(settings, 'PLANET_BASEMAP_MOSAIC', '')
        key = getattr(settings, 'PLANET_API_KEY', '')
        if mosaic and key:
            return f"https://tiles.planet.com/basemaps/v1/planet-tiles/{mosaic}/gmap/{{z}}/{{x}}/{{y}}.png?api_key={key}"
    except Exception:
        pass
    return ''


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
            "gj": alvo_geojson,
            "label": "Área da Propriedade",
            "area": f'{tamanho_area:.4f} ha',
            "color": "#000000",
            "fonte": "Área da Propriedade",
        }
    ]

    for p in poligonos_imoveis:
        items.append({
            "gj": p["polygon_geojson"],
            "label": p["item_info"],
            "area": f'{p["area"]:.4f} ha',
            "color": p["color"],
            "fonte": p["fonte"],
        })

    data['map_items'] = items
    return data
