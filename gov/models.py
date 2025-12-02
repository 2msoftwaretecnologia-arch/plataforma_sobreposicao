from django.db import models
from kernel.models import GeoBaseModel

# Create your models here.
class Sigef(GeoBaseModel):
    name = models.CharField(
        max_length=400, 
        verbose_name="Nome da area", 
        db_column='nome_area'
    )
    
    installment_code = models.CharField(
        max_length=150, 
        verbose_name="Código do imovel", 
        db_column='codigo_imo'
    )

    property_code = models.CharField(
        max_length=150, 
        verbose_name="Código do imovel", 
        db_column='propriedade_co'
    )

    status = models.CharField(
        max_length=150, 
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
        verbose_name = "Sigef"
        verbose_name_plural = "Sigef"

    def __str__(self):
        return self.name

class Ruralsettlement(GeoBaseModel):
    project_name = models.CharField(
        max_length=70, 
        verbose_name="Nome do projeto", 
        db_column='nome_proje'
    )
    
    method_obtaining = models.CharField(
        max_length=70, 
        verbose_name="Método de obtenção", 
        db_column='forma_obte'
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
        db_table = 'tb_assentamento_rural'
        verbose_name = "Assentamento rural"
        verbose_name_plural = "Assentamentos rurais"

    def __str__(self):
        return self.project_name


class SnicTotal(GeoBaseModel):
    property_name = models.CharField(
        max_length=150, 
        verbose_name="Nome do imovel", 
        db_column='nome_imove'
    )
    
    property_code = models.CharField(
        max_length=150, 
        verbose_name="Código do imovel", 
        db_column='cod_imovel'
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
        db_table = 'tb_snic_total'
        verbose_name = "Snic Total"
        verbose_name_plural = "Snic Total"

    def __str__(self):
        return self.property_name
