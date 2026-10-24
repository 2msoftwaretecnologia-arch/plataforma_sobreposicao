import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0006_searchhistory_kml'),
        ('mcp_connector', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='McpUpload',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_column='codigo', max_length=32, unique=True, verbose_name='Código')),
                ('kind', models.CharField(choices=[('area', 'Área (shapefile, KML/KMZ ou GeoJSON)'), ('demonstrativo', 'PDF do Demonstrativo do CAR'), ('recibo', 'PDF do Recibo do CAR')], db_column='tipo', max_length=20, verbose_name='Tipo')),
                ('label', models.CharField(blank=True, db_column='identificacao', default='', max_length=100, verbose_name='Identificação')),
                ('status', models.CharField(choices=[('pendente', 'Aguardando o arquivo'), ('processando', 'Processando'), ('concluido', 'Concluído'), ('erro', 'Erro')], db_column='situacao', default='pendente', max_length=20, verbose_name='Situação')),
                ('filename', models.CharField(blank=True, db_column='arquivo', default='', max_length=255, verbose_name='Arquivo')),
                ('error', models.TextField(blank=True, db_column='erro', default='', verbose_name='Erro')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='criado_em', verbose_name='Criado em')),
                ('finished_at', models.DateTimeField(blank=True, db_column='concluido_em', null=True, verbose_name='Concluído em')),
                ('analysis', models.ForeignKey(blank=True, db_column='analise_id', null=True, on_delete=django.db.models.deletion.SET_NULL, to='analysis.searchhistory', verbose_name='Análise')),
                ('user', models.ForeignKey(db_column='usuario_id', on_delete=django.db.models.deletion.CASCADE, related_name='mcp_uploads', to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
            ],
            options={
                'verbose_name': 'Envio de arquivo pelo assistente',
                'verbose_name_plural': 'Envios de arquivo pelo assistente',
                'db_table': 'tb_envio_mcp',
                'ordering': ['-created_at'],
            },
        ),
    ]
