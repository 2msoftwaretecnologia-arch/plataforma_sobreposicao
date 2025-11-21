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
