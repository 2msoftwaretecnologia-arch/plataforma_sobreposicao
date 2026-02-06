from django.db import models
from kernel.models import GeoBaseModel

class Highways(GeoBaseModel):
    NOME_2011 = models.CharField(
        max_length=255,
        verbose_name="Nome da via",
        db_column="NOME_2011",
        null=True,
        blank=True
    )

    CLAS_2011 = models.CharField(
        max_length=255,
        verbose_name="Tipo da via",
        db_column="CLAS_2011",
        null=True,
        blank=True
    )

    hash_id = models.CharField(
        max_length=64,
        verbose_name="Hash ID",
        db_column='hash_id',
        unique=True,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'tb_highways'
        verbose_name = "Rodovia"
        verbose_name_plural = "Rodovias"

    def __str__(self):
        return self.NOME_2011 or f"Rodovia {self.id}"
