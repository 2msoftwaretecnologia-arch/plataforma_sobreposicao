from core.read_files import _buscar_geometria_por_car
from .search_all import SearchAll


class BuscaPorCAR:
    def executar(self, numero_car):
        geometria_wkt = _buscar_geometria_por_car(numero_car)
        if not geometria_wkt or not str(geometria_wkt).strip():
            raise ValueError(
                f"Não foi possível localizar a geometria para o CAR {numero_car}."
            )

        return SearchAll().executar(geometria_wkt, excluir_car=numero_car)
