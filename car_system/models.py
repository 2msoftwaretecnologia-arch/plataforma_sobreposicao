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

class CarEstadual2023(GeoBaseModel):
    """Retrato do CAR estadual do Tocantins (área do imóvel) em 13/02/2023.
    Traz dados pessoais do proprietário/cadastrante, por isso a base nasce
    restrita ao grupo "Funcionários" (ver migration de LayerAccessPolicy)."""
    car_number = models.CharField(max_length=20, verbose_name="Número do CAR Estadual", db_column='numero_car', db_index=True)
    federal_car_number = models.CharField(max_length=43, null=True, blank=True, verbose_name="Número do CAR Federal", db_column='car_federal', db_index=True)
    property_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Nome do Imóvel", db_column='nome_imovel')
    status = models.CharField(max_length=50, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True, verbose_name="Município", db_column='municipio')
    ibge_code = models.IntegerField(null=True, blank=True, verbose_name="Código IBGE", db_column='cod_ibge')
    declared_area_ha = models.FloatField(null=True, blank=True, verbose_name="Área Declarada (ha)", db_column='area_declarada_ha')
    fiscal_modules = models.FloatField(null=True, blank=True, verbose_name="Módulos Fiscais", db_column='modulos_fiscais')
    registration_date = models.DateField(null=True, blank=True, verbose_name="Data do Cadastro", db_column='data_cadastro')
    contact_email = models.CharField(max_length=255, null=True, blank=True, verbose_name="E-mail de Contato", db_column='email_contato')
    contact_phone = models.CharField(max_length=50, null=True, blank=True, verbose_name="Telefone de Contato", db_column='telefone_contato')
    registrant_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Nome do Cadastrante", db_column='nome_cadastrante')
    area_type = models.CharField(max_length=50, null=True, blank=True, verbose_name="Tipo de Área", db_column='tipo_area')
    information = models.TextField(null=True, blank=True, verbose_name="Informações (proprietário)", db_column='informacoes')

    class Meta:
        db_table = 'tb_car_estadual_2023'
        verbose_name = "CAR Estadual (13/02/2023)"
        verbose_name_plural = "CAR Estadual (13/02/2023)"

    def __str__(self):
        return self.car_number


class DeclaredSicarTheme(GeoBaseModel):
    """Feições de um tema declarado no CAR, do download por estado do SICAR
    (consultapublica.car.gov.br, GeoPackage `TO_<TEMA>.gpkg`). Todos os temas
    (APP, vegetação nativa, reserva legal...) vêm com as mesmas colunas, então
    cada base só muda a tabela."""
    category_source = models.CharField(max_length=255, verbose_name="Tema", db_column='nom_tema')
    car_number = models.CharField(max_length=50, verbose_name="Número do CAR", db_column='cod_imovel', db_index=True)
    city = models.CharField(max_length=100, null=True, blank=True, verbose_name="Município", db_column='municipio')
    pending = models.CharField(max_length=255, null=True, blank=True, verbose_name="Condição do Cadastro", db_column='des_condic')
    car_status = models.CharField(max_length=10, null=True, blank=True, verbose_name="Status do CAR", db_column='ind_status')
    declared_area_ha = models.FloatField(null=True, blank=True, verbose_name="Área Declarada (ha)", db_column='num_area')

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.category_source} - {self.car_number}"


class DeclaredApp(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_app_declarada'
        verbose_name = "APP declarada"
        verbose_name_plural = "APPs declaradas"


class DeclaredNativeVegetation(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_vegetacao_nativa_declarada'
        verbose_name = "vegetação nativa declarada"
        verbose_name_plural = "vegetações nativas declaradas"


class DeclaredLegalReserve(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_reserva_legal_declarada'
        verbose_name = "reserva legal declarada"
        verbose_name_plural = "reservas legais declaradas"


class DeclaredConsolidatedArea(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_area_consolidada_declarada'
        verbose_name = "área consolidada declarada"
        verbose_name_plural = "áreas consolidadas declaradas"


class DeclaredRestrictedUse(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_uso_restrito_declarado'
        verbose_name = "área de uso restrito declarada"
        verbose_name_plural = "áreas de uso restrito declaradas"


class DeclaredFallowArea(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_area_pousio_declarada'
        verbose_name = "área de pousio declarada"
        verbose_name_plural = "áreas de pousio declaradas"


class DeclaredAdministrativeEasement(DeclaredSicarTheme):
    class Meta:
        db_table = 'tb_servidao_administrativa_declarada'
        verbose_name = "servidão administrativa declarada"
        verbose_name_plural = "servidões administrativas declaradas"
