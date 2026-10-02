import json

from django.db import migrations

TASK_NAME = "Atualizar alertas do MapBiomas pela API"


def agendar(apps, schema_editor):
    """Reimporta os alertas do MapBiomas Alerta toda segunda-feira, às 03:00
    de Brasília: o MapBiomas publica alertas novos toda semana."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="6", day_of_month="*", month_of_year="*", day_of_week="1", timezone="UTC",
    )
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": "control_panel.tasks.process_layer_task",
            "args": json.dumps(["DeforestationMapbiomas"]),
            "crontab": schedule,
            "enabled": True,
        },
    )


def desagendar(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("deforestation_fires", "0010_agendar_atualizacao_prodes"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(agendar, desagendar),
    ]
