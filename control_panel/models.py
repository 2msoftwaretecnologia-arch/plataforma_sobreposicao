from pickle import TRUE
from django.conf import settings
from django.db import models

from kernel.models import GeoBaseModel


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


class CustomLayer(models.Model):
    """Base de dados (SHP) criada pelo usuário pelo painel, sem precisar
    escrever um Model/Formatter/Importer novo em código. As feições ficam em
    `CustomLayerFeature` (uma tabela só, compartilhada por todas as bases
    customizadas) e as colunas escolhidas em `CustomLayerColumn`.

    `ativo=False` até o usuário confirmar (na tela) que os dados importados
    estão corretos — só então a base passa a entrar nas buscas de sobreposição
    de verdade (ver `FormatterRegister`).
    """
    nome = models.CharField(max_length=150)
    cor = models.CharField(max_length=7, default="#607D8B")
    ativo = models.BooleanField(default=False)
    arquivo = models.FileField(upload_to='documents/custom_layers/', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='custom_layers_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tb_custom_layer'
        verbose_name = "Base de Dados Customizada"
        verbose_name_plural = "Bases de Dados Customizadas"
        ordering = ['-created_at']

    def __str__(self):
        return self.nome

    @property
    def proxy_name(self):
        """Nome usado como chave da camada dentro do pipeline de análise
        (ver `analysis...formatter_register.py`) — precisa ser estável e
        recuperável de volta para este registro (ver `final_result_builder.py`)."""
        return f"CustomLayer__{self.id}"


class CustomLayerColumn(models.Model):
    layer = models.ForeignKey(CustomLayer, related_name='colunas', on_delete=models.CASCADE)
    coluna_origem = models.CharField(max_length=100, help_text="Nome da coluna no shapefile original")
    rotulo = models.CharField(max_length=150)
    incluir = models.BooleanField(default=True, help_text="Aparece no resultado da análise de sobreposição")
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'tb_custom_layer_column'
        ordering = ['ordem', 'id']
        constraints = [
            models.UniqueConstraint(fields=['layer', 'coluna_origem'], name='uniq_custom_layer_column')
        ]

    def __str__(self):
        return f"{self.layer.nome}.{self.coluna_origem}"


class CustomLayerFeature(GeoBaseModel):
    """Uma feição (linha do shapefile) de uma base customizada. Todas as
    bases customizadas compartilham esta única tabela (filtradas por
    `layer`) — assim, criar uma base nova pelo painel nunca exige uma
    migração de banco."""
    layer = models.ForeignKey(CustomLayer, related_name='features', on_delete=models.CASCADE, db_index=True)
    atributos = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'tb_custom_layer_feature'
        verbose_name = "Feição de Base Customizada"
        verbose_name_plural = "Feições de Bases Customizadas"

