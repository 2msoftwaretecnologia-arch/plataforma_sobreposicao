import json

from django.db import migrations

TASK_NAME = "Atualizar PRODES pela API do INPE"


def agendar(apps, schema_editor):
    """Reimporta o PRODES (API do INPE/TerraBrasilis) todo dia 5, às 03:00 de
    Brasília. O INPE publica o PRODES uma vez por ano (e às vezes corrige);
    checar todo mês pega a nova versão sem ninguém precisar lembrar."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="6", day_of_month="5", month_of_year="*", day_of_week="*", timezone="UTC",
    )
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": "control_panel.tasks.process_layer_task",
            "args": json.dumps(["Prodes"]),
            "crontab": schedule,
            "enabled": True,
        },
    )


def desagendar(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("deforestation_fires", "0009_prodes"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(agendar, desagendar),
    ]
