from django.db import models


class SicarRecord(models.Model):
    car_number = models.CharField(
        max_length=43,
        unique=True,
        verbose_name="Número do CAR",
        db_column='numero_car'
    )
    status = models.CharField(max_length=50)
    geo_coordinates = models.TextField(
        verbose_name="Coordenadas Geográficas",
        db_column='coordenadas_geograficas'
    )

    class Meta:
        db_table = 'tb_registro_sicar'
        verbose_name = "Registro do SICAR"
        verbose_name_plural = "Registros do SICAR"

    def __str__(self):
        return self.car_number