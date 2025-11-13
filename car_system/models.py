from kernel.models import GeoBaseModel
from django.db import models

class SicarRecord(GeoBaseModel):
    car_number = models.CharField(
        max_length=43,
        unique=True,
        verbose_name="Número do CAR",
        db_column='numero_car'
    )

    hash_id = models.CharField(
        max_length=64, 
        verbose_name="Hash ID", 
        db_column='hash_id', 
        unique=True, 
        null=True, 
        blank=True
    )
    
    status = models.CharField(max_length=50)

    class Meta:
        db_table = 'tb_registro_sicar'
        verbose_name = "Registro do SICAR"
        verbose_name_plural = "Registros do SICAR"

    def __str__(self):
        return self.car_number