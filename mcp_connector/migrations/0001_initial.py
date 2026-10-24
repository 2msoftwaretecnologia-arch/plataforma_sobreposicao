import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='McpAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tool', models.CharField(db_column='ferramenta', max_length=80, verbose_name='Ferramenta')),
                ('arguments', models.JSONField(blank=True, db_column='argumentos', default=dict, verbose_name='Argumentos')),
                ('success', models.BooleanField(db_column='sucesso', default=True, verbose_name='Sucesso')),
                ('error', models.TextField(blank=True, db_column='erro', verbose_name='Erro')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='criado_em', db_index=True, verbose_name='Criado em')),
                ('user', models.ForeignKey(db_column='usuario_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mcp_audit_logs', to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
            ],
            options={
                'verbose_name': 'Consulta pelo assistente',
                'verbose_name_plural': 'Consultas pelo assistente',
                'db_table': 'tb_auditoria_mcp',
                'ordering': ['-created_at'],
            },
        ),
    ]
