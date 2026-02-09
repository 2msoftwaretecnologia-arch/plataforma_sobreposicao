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


class Embargoes(GeoBaseModel):
    property_name = models.CharField(
        max_length=250, 
        verbose_name="Nome do imovel", 
        db_column='nome_imove'
    )
    
    type_area = models.CharField(
        max_length=70, 
        verbose_name="Tipo de area", 
        db_column='tipo_area'
    )
    number_infraction_act = models.CharField(
        max_length=70, 
        verbose_name="numero do ato de infracao", 
        db_column='num_auto_i'
    )
    nome_embargado = models.CharField(
        max_length=100, 
        verbose_name="Nome do embargado", 
        db_column='nome_embar'
    )
    cpf_cnpj_embargado = models.CharField(
        max_length=70, 
        verbose_name="CPF/CNPJ do embargado", 
        db_column='cpf_cnpj_e'
    )
    control_unity = models.CharField(
        max_length=100, 
        verbose_name="Unidade controladora", 
        db_column='unid_contr'
    )
    process_number = models.CharField(
        max_length=70, 
        verbose_name="Numero do processo", 
        db_column='num_proce'
    )
    act_description = models.CharField(
        max_length=100, 
        verbose_name="Descricao do ato de infracao", 
        db_column='des_tad'
    )
    infraction_description = models.CharField(
        max_length=100, 
        verbose_name="Descricao do infracao", 
        db_column='des_infrac'
    )
    embargoe_date = models.CharField(
        max_length=70, 
        verbose_name="Data do embargado", 
        db_column='data_embarg'
    )
    priting_date = models.CharField(
        max_length=70, 
        verbose_name="Data de impressao", 
        db_column='data_impres'
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
        db_table = 'tb_embargoes'
        verbose_name = "Embargoes"
        verbose_name_plural = "Embargoes"

    def __str__(self):
        return self.property_name
