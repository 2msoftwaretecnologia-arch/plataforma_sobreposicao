from typing import Any, Dict, List
from car_system.models import SicarRecord

class SicarRecordLoader:
    
    @staticmethod
    def load(car) -> List[Dict[str, Any]]:
        if car.strip():
            return SicarRecordLoader().load_by_exclusion(exclude_car=car)
        else:
            return SicarRecordLoader().load_all()

    @staticmethod
    def load_all() -> List[Dict[str, Any]]:
        sicar_record_areas = SicarRecord.objects.all()
        sicar_record_data = []

        for sicar in sicar_record_areas:
            sicar_record_data.append({
                'wkt': sicar.geometry,
                'numero_car': sicar.car_number,
                'sigla_zona': sicar.status
            })
        
        return sicar_record_data
    
    def load_by_exclusion(self, exclude_car: str) -> List[Dict[str, Any]]:
        sicar_record_areas = SicarRecord.objects.exclude(car_number=exclude_car)
        sicar_record_data = []

        for sicar in sicar_record_areas:
            sicar_record_data.append({
                'wkt': sicar.geometry,
                'numero_car': sicar.car_number,
                'sigla_zona': sicar.status
            })
        
        return sicar_record_data