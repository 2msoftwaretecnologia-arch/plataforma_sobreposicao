from pickle import TRUE
from django.db import models


class StorageSnapshot(models.Model):
    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    database_size_bytes = models.BigIntegerField(verbose_name="Tamanho do Banco (bytes)")
    disk_used_bytes = models.BigIntegerField(verbose_name="Disco Utilizado (bytes)")
    disk_total_bytes = models.BigIntegerField(verbose_name="Disco Total (bytes)")
    hostname = models.CharField(max_length=255, default='', blank=True, verbose_name="Servidor")

    class Meta:
        db_table = 'tb_armazenamento_snapshot'
        verbose_name = "Snapshot de Armazenamento"
        verbose_name_plural = "Snapshots de Armazenamento"
        ordering = ['-captured_at']

    def __str__(self):
        return f"Snapshot {self.captured_at:%d/%m/%Y %H:%M}"


class FileManagement(models.Model):
    phytoecology_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Fitoecologia",
        help_text="Arquivo ZIP contendo dados da Área de Fitoecologia."
    )

    environmental_protection_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Proteção Ambiental",
        help_text="Arquivo ZIP contendo dados da Área de Proteção Ambiental."
    )

    zoning_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Zoneamento",
        help_text="Arquivo ZIP contendo dados da Área de Zoneamento."
    )

    sicar_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos SICAR",
        help_text="Arquivo ZIP contendo dados da Área SICAR."
    )

    indigenous_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Terra Indígena",
        help_text="Arquivo ZIP contendo dados da Área de Terra Indígena.",
        null = True,
        blank = True
    )

    quilombolas_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Quilombolas",
        help_text="Arquivo ZIP contendo dados da Área de Quilombolas.",
        null = True,
        blank = True
    )
    
    paths_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Veredas",
        help_text="Arquivo ZIP contendo dados da Área de Veredas.",
        null = True,
        blank = True
    )

    conservation_units_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Unidades de Conservação",
        help_text="Arquivo ZIP contendo dados da Área de Unidades de Conservação.",
        null = True,
        blank = True
    )
    
    municipal_boundaries_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Municípios",
        help_text="Arquivo ZIP contendo dados da Área de Municípios.",
        null = True,
        blank = True
    )
    
    sigef_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Sigef",
        help_text="Arquivo ZIP contendo dados da Área de Sigef.",
        null = True,
        blank = True
    )
    
    ruralsettlement_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Assentamento Rural",
        help_text="Arquivo ZIP contendo dados da Área de Assentamento Rural.",
        null = True,
        blank = True
    )
    
    snic_total_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos SNIC Total",
        help_text="Arquivo ZIP contendo dados da Área de SNIC Total.",
        null = True,
        blank = True
    )
    
    deforestation_mapbiomas_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Mapa de Deforestação",
        help_text="Arquivo ZIP contendo dados da Área de Mapa de Deforestação.",
        null = True,
        blank = True
    )

    highways_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Highways",
        help_text="Arquivo ZIP contendo dados da Área de Highways.",
        null = True,
        blank = True
    )
    ipuca_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Ipuca",
        help_text="Arquivo ZIP contendo dados da Área de Ipuca.",
        null = True,
        blank = True
    )

    adm_embargos_ibama_a_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Embargos IBAMA A",
        help_text="Arquivo ZIP contendo dados da Área de Embargos IBAMA A.",
        null = True,
        blank = True
    )
    
    prodes_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Prodes",
        help_text="Arquivo ZIP contendo dados da Área de Prodes.",
        null = True,
        blank = True
    )

    hydrography_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Hidrografia Declarada",
        help_text="Arquivo ZIP contendo dados da Área de Hidrografia Declarada.",
        null = True,
        blank = True
    )

    car_estadual_2023_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos CAR Estadual (13/02/2023)",
        help_text="Arquivo ZIP contendo o shapefile do CAR Estadual (área do imóvel) de 13/02/2023.",
        null = True,
        blank = True
    )

    # Temas declarados no CAR, do download por estado do SICAR (TO_<TEMA>.gpkg).
    declared_app_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos APP Declarada",
        help_text="GeoPackage do SICAR (TO_APPS.gpkg) ou ZIP com o shapefile das APPs declaradas.",
        null = True,
        blank = True
    )

    declared_native_vegetation_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Vegetação Nativa Declarada",
        help_text="GeoPackage do SICAR (TO_VEGETACAO_NATIVA.gpkg) ou ZIP com o shapefile da vegetação nativa declarada.",
        null = True,
        blank = True
    )

    declared_legal_reserve_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Reserva Legal Declarada",
        help_text="GeoPackage do SICAR (TO_RESERVA_LEGAL.gpkg) ou ZIP com o shapefile das reservas legais declaradas.",
        null = True,
        blank = True
    )

    declared_consolidated_area_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Área Consolidada Declarada",
        help_text="GeoPackage do SICAR (TO_AREA_CONSOLIDADA.gpkg) ou ZIP com o shapefile das áreas consolidadas declaradas.",
        null = True,
        blank = True
    )

    declared_restricted_use_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Uso Restrito Declarado",
        help_text="GeoPackage do SICAR (TO_USO_RESTRITO.gpkg) ou ZIP com o shapefile das áreas de uso restrito declaradas.",
        null = True,
        blank = True
    )

    declared_fallow_area_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Área de Pousio Declarada",
        help_text="GeoPackage do SICAR (TO_AREA_POUSIO.gpkg) ou ZIP com o shapefile das áreas de pousio declaradas.",
        null = True,
        blank = True
    )

    declared_administrative_easement_zip_file = models.FileField(
        upload_to='documents/',
        verbose_name="Documentos Servidão Administrativa Declarada",
        help_text="GeoPackage do SICAR (TO_SERVIDAO_ADMINISTRATIVA.gpkg) ou ZIP com o shapefile das servidões administrativas declaradas.",
        null = True,
        blank = True
    )

    class Meta:
        db_table = 'tb_gerenciamento_arquivos'
        verbose_name = "Gerenciamento de Arquivos"
        verbose_name_plural = "Gerenciamento de Arquivos"

    def __str__(self):
        return f"Gerenciamento de Arquivos"


class LayerFieldToggle(models.Model):
    """Liga/desliga um campo de uma base no resultado da análise de
    sobreposição. `modelo` é o nome da classe do Model da camada (ex:
    'ZoningArea') e `campo` é a chave devolvida pelo Formatter dessa camada
    (ex: 'zona') — ver `bases_config.get_toggleable_fields`.

    Ausência de registro = campo ligado (comportamento padrão, sem opt-in).
    """
    modelo = models.CharField(max_length=100, db_index=True)
    campo = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tb_layer_field_toggle'
        verbose_name = "Coluna do Resultado da Análise"
        verbose_name_plural = "Colunas do Resultado da Análise"
        constraints = [
            models.UniqueConstraint(fields=['modelo', 'campo'], name='uniq_layer_field_toggle')
        ]

    def __str__(self):
        return f"{self.modelo}.{self.campo} ({'ativo' if self.ativo else 'inativo'})"



class LayerAccessPolicy(models.Model):
    """Ausência de política mantém a base disponível aos usuários da plataforma."""
    modelo = models.CharField(max_length=100, unique=True)
    restrita = models.BooleanField(default=False)
    grupos = models.ManyToManyField('auth.Group', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tb_layer_access_policy'
