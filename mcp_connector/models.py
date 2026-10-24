from django.conf import settings
from django.db import models


class McpAuditLog(models.Model):
    """Uma chamada de ferramenta feita por um assistente (Claude, ChatGPT) em nome de um usuário."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='mcp_audit_logs',
        on_delete=models.SET_NULL,
        null=True,
        db_column='usuario_id',
        verbose_name='Usuário',
    )
    tool = models.CharField(max_length=80, db_column='ferramenta', verbose_name='Ferramenta')
    arguments = models.JSONField(default=dict, blank=True, db_column='argumentos', verbose_name='Argumentos')
    success = models.BooleanField(default=True, db_column='sucesso', verbose_name='Sucesso')
    error = models.TextField(blank=True, db_column='erro', verbose_name='Erro')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, db_column='criado_em', verbose_name='Criado em')

    class Meta:
        db_table = 'tb_auditoria_mcp'
        ordering = ['-created_at']
        verbose_name = 'Consulta pelo assistente'
        verbose_name_plural = 'Consultas pelo assistente'

    def __str__(self):
        return f'{self.tool} ({self.created_at:%d/%m/%Y %H:%M})'


class McpUpload(models.Model):
    """Link de envio de arquivo pedido pelo assistente.

    O assistente não repassa arquivos binários (shapefile, KMZ, PDF), então
    entrega ao usuário um link de uso único (`code`) para enviá-lo pela
    plataforma; a análise feita com o arquivo fica em `analysis`, e o
    assistente a busca pelo código (`resultado_envio`).
    """

    class Kind(models.TextChoices):
        AREA = 'area', 'Área (shapefile, KML/KMZ ou GeoJSON)'
        DEMONSTRATIVO = 'demonstrativo', 'PDF do Demonstrativo do CAR'
        RECIBO = 'recibo', 'PDF do Recibo do CAR'

    class Status(models.TextChoices):
        PENDING = 'pendente', 'Aguardando o arquivo'
        PROCESSING = 'processando', 'Processando'
        DONE = 'concluido', 'Concluído'
        ERROR = 'erro', 'Erro'

    code = models.CharField(max_length=32, unique=True, db_column='codigo', verbose_name='Código')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='mcp_uploads', on_delete=models.CASCADE,
        db_column='usuario_id', verbose_name='Usuário',
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, db_column='tipo', verbose_name='Tipo')
    label = models.CharField(max_length=100, blank=True, default='', db_column='identificacao',
                             verbose_name='Identificação')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING,
                              db_column='situacao', verbose_name='Situação')
    filename = models.CharField(max_length=255, blank=True, default='', db_column='arquivo', verbose_name='Arquivo')
    analysis = models.ForeignKey(
        'analysis.SearchHistory', null=True, blank=True, on_delete=models.SET_NULL,
        db_column='analise_id', verbose_name='Análise',
    )
    error = models.TextField(blank=True, default='', db_column='erro', verbose_name='Erro')
    created_at = models.DateTimeField(auto_now_add=True, db_column='criado_em', verbose_name='Criado em')
    finished_at = models.DateTimeField(null=True, blank=True, db_column='concluido_em', verbose_name='Concluído em')

    class Meta:
        db_table = 'tb_envio_mcp'
        ordering = ['-created_at']
        verbose_name = 'Envio de arquivo pelo assistente'
        verbose_name_plural = 'Envios de arquivo pelo assistente'

    def __str__(self):
        return f'{self.get_kind_display()} ({self.created_at:%d/%m/%Y %H:%M})'
