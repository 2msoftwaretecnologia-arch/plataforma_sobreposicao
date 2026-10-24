from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('control_panel', '0022_filemanagement_declared_sicar_themes'),
    ]

    operations = [
        migrations.CreateModel(
            name='LayerUpdate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modelo', models.CharField(db_index=True, max_length=100)),
                ('total', models.PositiveIntegerField(default=0)),
                ('finished_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Atualização de base',
                'verbose_name_plural': 'Atualizações de bases',
                'db_table': 'tb_atualizacao_base',
                'ordering': ['-finished_at'],
            },
        ),
    ]
