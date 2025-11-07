import requests
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon
import unicodedata


def localizar_cidade_estado(wkt_str: str, method: str = "representative") -> tuple[str | None, str | None]:
    """
    Recebe um polígono em WKT (POLYGON ou MULTIPOLYGON) em WGS84 (lon lat)
    e retorna (cidade, estado) usando o Nominatim.

    method:
        - 'representative' -> pega um ponto garantidamente dentro da geometria
        - 'centroid'       -> pega o centro geométrico
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
    HEADERS = {"User-Agent": "PlataformaSobreposicao/1.0 (contato@example.com)"}

    # --- Carregar a geometria ---
    try:
        geom = wkt.loads(wkt_str)
    except Exception:
        return None, None

    if not isinstance(geom, (Polygon, MultiPolygon)):
        return None, None

    # --- Definir ponto de consulta ---
    pt = geom.representative_point() if method == "representative" else geom.centroid
    lon, lat = pt.x, pt.y

    # --- Consulta reversa ---
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "accept-language": "pt-BR",
        "addressdetails": 1,
    }

    try:
        r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None, None

    addr = data.get("address", {})
    cidade = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("city_district")
        or addr.get("county")
    )
    estado = addr.get("state")

    # Converter nome do estado para UF
    uf = _estado_para_uf(estado) if estado else None

    return cidade, uf


def _estado_para_uf(nome_estado: str | None) -> str | None:
    if not nome_estado:
        return None

    # Normalizar para remover acentos e comparar em lower
    def normalize(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode().lower().strip()

    estados_uf = {
        "acre": "AC",
        "alagoas": "AL",
        "amapa": "AP",
        "amazonas": "AM",
        "bahia": "BA",
        "ceara": "CE",
        "distrito federal": "DF",
        "espirito santo": "ES",
        "goias": "GO",
        "maranhao": "MA",
        "mato grosso": "MT",
        "mato grosso do sul": "MS",
        "minas gerais": "MG",
        "para": "PA",
        "paraiba": "PB",
        "parana": "PR",
        "pernambuco": "PE",
        "piaui": "PI",
        "rio de janeiro": "RJ",
        "rio grande do norte": "RN",
        "rio grande do sul": "RS",
        "rondonia": "RO",
        "roraima": "RR",
        "santa catarina": "SC",
        "sao paulo": "SP",
        "sergipe": "SE",
        "tocantins": "TO",
    }

    key = normalize(nome_estado)
    # alguns retornos do nominatim podem vir com prefixos
    # ex: "estado de são paulo" => vamos remover possíveis prefixos
    for k in estados_uf.keys():
        if key.endswith(k) or key == k:
            return estados_uf[k]

    return None