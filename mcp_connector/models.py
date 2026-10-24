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
