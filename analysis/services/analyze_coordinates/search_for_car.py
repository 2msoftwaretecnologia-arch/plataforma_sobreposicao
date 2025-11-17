from car_system.utils import get_sicar_record
from .search_all import SearchAll


class SearchForCar:
    
    def execute(self, car: str) -> dict:
        car_searched = get_sicar_record(car_number=car)

        if not car_searched.exists():
            return {}
        
        if not car_searched.first().geometry:
            return {}
        
        geometria_wkt = car_searched.first().geometry
        
        return SearchAll().execute(geometria_wkt, car=car)
