from cores_log import log_print, color_print
class CacheManager:
    def __init__(self):
        # Caches e timestamps
        self._cache_imoveis = None
        self._cache_timestamp_imoveis = None

        self._cache_zoneamento = None
        self._cache_timestamp_zoneamento = None

        self._cache_fito_ecologias = None
        self._cache_timestamp_fito_ecologias = None

        self._cache_apas = None
        self._cache_timestamp_apas = None

        self.cache_verificador = None

    # --- Getters e Setters para imóveis ---
    @property
    def cache_imoveis(self):
        return self._cache_imoveis

    @cache_imoveis.setter
    def cache_imoveis(self, value):
        self._cache_imoveis = value

    @property
    def cache_timestamp_imoveis(self):
        return self._cache_timestamp_imoveis

    @cache_timestamp_imoveis.setter
    def cache_timestamp_imoveis(self, value):
        self._cache_timestamp_imoveis = value

    # --- Zoneamento ---
    @property
    def cache_zoneamento(self):
        return self._cache_zoneamento

    @cache_zoneamento.setter
    def cache_zoneamento(self, value):
        self._cache_zoneamento = value

    @property
    def cache_timestamp_zoneamento(self):
        return self._cache_timestamp_zoneamento

    @cache_timestamp_zoneamento.setter
    def cache_timestamp_zoneamento(self, value):
        self._cache_timestamp_zoneamento = value

    # --- Fitoecologias ---
    @property
    def cache_fito_ecologias(self):
        return self._cache_fito_ecologias

    @cache_fito_ecologias.setter
    def cache_fito_ecologias(self, value):
        self._cache_fito_ecologias = value

    @property
    def cache_timestamp_fito_ecologias(self):
        return self._cache_timestamp_fito_ecologias

    @cache_timestamp_fito_ecologias.setter
    def cache_timestamp_fito_ecologias(self, value):
        self._cache_timestamp_fito_ecologias = value

    # --- APAs ---
    @property
    def cache_apas(self):
        return self._cache_apas

    @cache_apas.setter
    def cache_apas(self, value):
        self._cache_apas = value

    @property
    def cache_timestamp_apas(self):
        return self._cache_timestamp_apas

    @cache_timestamp_apas.setter
    def cache_timestamp_apas(self, value):
        self._cache_timestamp_apas = value

    # --- Verificador Global ---
    @property
    def cache_verificador(self):
        return self._cache_verificador

    @cache_verificador.setter
    def cache_verificador(self, value):
        self._cache_verificador = value

# Singleton de cache para uso em todo o projeto
cache = CacheManager()

