from django.db import models
from kernel.models import GeoBaseModel

# Create your models here.
class Sigef(GeoBaseModel):
    name = models.CharField(
        max_length=70, 
        verbose_name="Nome da area", 
        db_column='nome_area'
    )
    
    installment_code = models.CharField(
        max_length=70, 
        verbose_name="Código do imovel", 
        db_column='codigo_imo'
    )

    property_code = models.CharField(
        max_length=70, 
        verbose_name="Código do imovel", 
        db_column='propriedade_co'
    )

    status = models.CharField(
        max_length=70, 
        verbose_name="Status", 
        db_column='status'
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
        db_table = 'tb_area_sigef'
        verbose_name = "Área da area"
        verbose_name_plural = "Nome das areas"

    def __str__(self):
        return self.name
