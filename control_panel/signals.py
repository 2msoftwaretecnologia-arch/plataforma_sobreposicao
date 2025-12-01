import os
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.conf import settings
from control_panel.models import FileManagement


@receiver(pre_save, sender=FileManagement)
def delete_old_files_on_update(sender, instance, **kwargs):
    # Se for criação, não faz nada
    if instance._state.adding:
        return

    try:
        old_instance = FileManagement.objects.get(pk=instance.pk)
    except FileManagement.DoesNotExist:
        return

    # Percorre TODOS os campos do modelo
    for field in instance._meta.fields:
        if isinstance(field, models.FileField):
            field_name = field.name

            old_file = getattr(old_instance, field_name)
            new_file = getattr(instance, field_name)

            # Se o arquivo mudou (ou foi removido)
            if old_file and old_file != new_file:
                old_path = old_file.path

                if os.path.isfile(old_path):
                    os.remove(old_path)
                    print(f"[CLEANUP] Arquivo removido: {old_path}")
