from django.db import models
from kernel.models import GeoBaseModel

# Create your models here.
class Quilombolas(GeoBaseModel):
    name = models.CharField(
        max_length=70, 
        verbose_name="Nome da Quilombola", 
        db_column='nm_comunid'
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
        db_table = 'tb_area_quilombolas'
        verbose_name = "Área de Quilombola"
        verbose_name_plural = "Áreas de Quilombolas"

    def __str__(self):
        return self.name

class Paths(GeoBaseModel):
    
    hash_id = models.CharField(
        max_length=64, 
        verbose_name="Hash ID", 
        db_column='hash_id', 
        unique=True, 
        null=True, 
        blank=True
    )
   
    class Meta:
        db_table = 'tb_area_veredas'
        verbose_name = "Área de Vereda"
        verbose_name_plural = "Áreas de Veredas"

class ConservationUnits(GeoBaseModel):
    unit = models.CharField(
        max_length=70, 
        verbose_name="Unidade de Conservação", 
        db_column='Unidades'
    )
    
    domain = models.CharField(
        max_length=70, 
        verbose_name="Domínio", 
        db_column='Dominios'
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
        db_table = 'tb_area_unidades_conservacao'
        verbose_name = "Unidade de Conservação"
        verbose_name_plural = "Unidades de Conservação"
