from datetime import date
from urllib.parse import urlencode

def build_mapbiomas_url(
    alert_code: str,
    start_month="2018-01",
    end_month=None,
    map_position="-9.656514,-49.901149,16",
):
    """Link do alerta no mapa do MapBiomas. O mapa só mostra alertas dentro do
    período filtrado: começa antes do primeiro alerta (nov/2018) e termina no
    mês atual, para os alertas novos da atualização semanal aparecerem."""
    base_url = "https://plataforma.alerta.mapbiomas.org/mapa"
    end_month = end_month or date.today().strftime("%Y-%m")

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
