from celery import shared_task
from deforestation_fires.tasks.deforestation_mapbiomas_importer import DeforestationMapbiomasImporter
from deforestation_fires.tasks.embargoe_importer import EmbargoesImporter


@shared_task
def import_deforestation_mapbiomas_task():
    DeforestationMapbiomasImporter().execute()

@shared_task
def import_embargoe_task():
    EmbargoesImporter().execute()
