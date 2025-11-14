import requests
import unicodedata
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon
from typing import Optional, Tuple


class CityStateLocatorService:
    """
    Service responsible for locating the city and state (UF) from a WKT geometry.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
    HEADERS = {"User-Agent": "OverlayPlatform/1.0 (contact@example.com)"}

    STATES_MAP = {
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

    def locate(self, wkt_str: str, method: str = "representative") -> Tuple[Optional[str], Optional[str]]:
        """
        Main flow: receives a WKT polygon and returns (city, state UF).
        """
        geometry = self._load_geometry(wkt_str)
        if geometry is None:
            return None, None

        lon, lat = self._extract_lookup_point(geometry, method)
        json_data = self._query_nominatim(lat, lon)

        if not json_data:
            return None, None

        city = self._extract_city(json_data)
        state_name = json_data.get("address", {}).get("state")
        uf = self._state_to_uf(state_name) if state_name else None

        return city, uf

    # -------------------------------------------------------------------------
    #                              PRIVATE METHODS
    # -------------------------------------------------------------------------

    def _load_geometry(self, wkt_str: str):
        try:
            geometry = wkt.loads(wkt_str)
        except Exception:
            return None

        if not isinstance(geometry, (Polygon, MultiPolygon)):
            return None

        return geometry

    def _extract_lookup_point(self, geometry, method: str):
        if method == "representative":
            point = geometry.representative_point()
        else:
            point = geometry.centroid
        return point.x, point.y  # lon, lat

    def _query_nominatim(self, lat: float, lon: float):
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "accept-language": "pt-BR",
            "addressdetails": 1,
        }

        try:
            response = requests.get(
                self.NOMINATIM_URL,
                params=params,
                headers=self.HEADERS,
                timeout=20
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _extract_city(self, data: dict) -> Optional[str]:
        address = data.get("address", {})

        return (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("city_district")
            or address.get("county")
        )

    # ------------------------ STATE NAME → UF --------------------------------

    def _state_to_uf(self, state_name: str) -> Optional[str]:
        normalized = self._normalize(state_name)

        for key in self.STATES_MAP.keys():
            # Handles cases like "Estado de São Paulo"
            if normalized.endswith(key) or normalized == key:
                return self.STATES_MAP[key]

        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return unicodedata.normalize("NFKD", value).encode("ASCII", "ignore").decode().lower().strip()
