from django.db import models
from kernel.models import GeoBaseModel

# Create your models here.
class DeforestationMapbiomas(GeoBaseModel):
    alert_code = models.CharField(
        max_length=70, 
        verbose_name="Código do alerta", 
        db_column='CODEALERTA'
    )
    
    detection_year = models.CharField(
        max_length=70, 
        verbose_name="Ano de detecção", 
        db_column='ANODETEC'
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
        db_table = 'tb_area_deforestation_mapbiomas'
        verbose_name = "Deforestation Mapbiomas"
        verbose_name_plural = "Deforestation Mapbiomas"

    def __str__(self):
        return self.alert_code
