from kernel.models import GeoBaseModel
from django.db import models
from django.db.models.functions import Upper

class SicarRecord(GeoBaseModel):
    car_number = models.CharField(
        max_length=43,
        unique=True,
        verbose_name="Número do CAR",
        db_column='numero_car'
    )
    
    last_update = models.DateField(
        verbose_name="Última Atualização",
        db_column='ultima_atualizacao',
        null=True,
        blank=True
    )
    
    status = models.CharField(max_length=50)

    class Meta:
        db_table = 'tb_registro_sicar'
        verbose_name = "Registro do SICAR"
        verbose_name_plural = "Registros do SICAR"
        indexes = [
            # As buscas por CAR usam `car_number__iexact` (ver
            # `car_system/utils.py`), que no Postgres vira
            # `UPPER(car_number) = UPPER(%s)` — um índice comum em
            # `car_number` não é usado nessa comparação, só um índice
            # funcional sobre `UPPER(car_number)`.
            models.Index(Upper('car_number'), name='idx_sicar_car_number_upper'),
        ]

    def __str__(self):
        return self.car_number