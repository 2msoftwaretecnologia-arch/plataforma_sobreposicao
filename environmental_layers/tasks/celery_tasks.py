from celery import shared_task
from environmental_layers.tasks.indigenous_area_importer import IndigenousAreaImporter
from environmental_layers.tasks.protection_area_importer import EnvironmentalProtectionAreaImporter
from environmental_layers.tasks.zoning_importer import ZoningAreaImporter
from environmental_layers.tasks.phytoecology_importer import PhytoecologyAreaImporter


@shared_task
def import_indigenous_area_task():
    IndigenousAreaImporter().execute()


@shared_task
def import_protection_area_task():
    EnvironmentalProtectionAreaImporter().execute()


@shared_task
def import_zoning_area_task():
    ZoningAreaImporter().execute()


@shared_task
def import_phytoecology_area_task():
    PhytoecologyAreaImporter().execute()

