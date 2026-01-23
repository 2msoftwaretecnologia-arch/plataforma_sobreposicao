from urllib.parse import urlencode

def build_mapbiomas_url(
    alert_code: str,
    start_month="2019-01",
    end_month="2025-11",
    map_position="-9.656514,-49.901149,16",
):
    base_url = "https://plataforma.alerta.mapbiomas.org/mapa"

    params = {
        "monthRange[0]": start_month,
        "monthRange[1]": end_month,
        "sources[0]": "All",
        "territoryType": "all",
        "authorization": "all",
        "embargoed": "all",
        "locationType": "alert_code",
        "locationText": f"{alert_code} ",
        "activeBaseMap": 1,
        "map": map_position,
    }

    return f"{base_url}?{urlencode(params)}"
