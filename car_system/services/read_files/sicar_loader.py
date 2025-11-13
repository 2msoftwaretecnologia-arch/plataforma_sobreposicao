from car_system.models import SicarRecord

class SicarRecordLoader:
    
    @staticmethod
    def load_sicar_record__data():
        sicar_record_areas = SicarRecord.objects.all()
        sicar_record_data = []

        for sicar in sicar_record_areas:
            sicar_record_data.append({
                'wkt': sicar.geometry,
                'numero_car': sicar.car_number,
                'sigla_zona': sicar.status
            })
        
        return sicar_record_data
