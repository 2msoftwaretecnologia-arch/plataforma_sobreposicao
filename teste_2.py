from car_system.models import SicarRecord
from environmental_layers.models import (
    PhytoecologyArea,
    EnvironmentalProtectionArea,
    ZoningArea
)
from kernel.service.teste import SicarOverlapService 
from pprint import pprint as pp 
# Buscar CAR específico
car = SicarRecord.objects.get(car_number="TO-1708304-C30DAD67AF79401DAD1B806E492F8A4C")

service = SicarOverlapService(car)

camadas = [
    PhytoecologyArea,
    EnvironmentalProtectionArea,
    ZoningArea,
    SicarRecord 
]

resultado = service.verificar_todas(camadas)

pp(resultado)
