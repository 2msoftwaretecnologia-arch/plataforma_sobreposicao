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
    

class DeclaredHydrography(GeoBaseModel):
    category_source = models.CharField(
        max_length=100, 
        verbose_name="Categoria do Recurso", 
        db_column='nom_tema'
    )
    
    car_number = models.CharField(
        max_length=50, 
        verbose_name="Número do CAR", 
        db_column='cod_imovel'
    )

    pending = models.CharField(
        max_length=100,
        verbose_name="Pendentes de Declaração",
        db_column='des_condic'
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
        db_table = 'tb_hidrografia_declarada'
        verbose_name = "hidrográfia declarada"
        verbose_name_plural = "hidrográfias declaradas"

    def __str__(self):
        return self.category_source