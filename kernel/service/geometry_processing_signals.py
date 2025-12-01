from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver

from kernel.models import GeoBaseModel
from kernel.service.geometry_processing_service import GeometryProcessingService


def _should_process(instance, created, **kwargs):
    if getattr(instance, "_geo_processing_guard", False):
        return False
    update_fields = kwargs.get("update_fields")
    if created:
        return True
    if update_fields is None:
        return True
    return "geometry" in update_fields


def _handler(sender, instance, created, **kwargs):
    if not _should_process(instance, created, **kwargs):
        return
    service = GeometryProcessingService(sender)
    service.process_instance(instance)


def register_geometry_processing_signals():
    for model in apps.get_models():
        if isinstance(model, type) and issubclass(model, GeoBaseModel):
            uid = f"geo_processing_{model._meta.label_lower}"
            post_save.connect(_handler, sender=model, dispatch_uid=uid)

