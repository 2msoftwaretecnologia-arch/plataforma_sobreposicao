from celery import shared_task
from deforestation_fires.tasks.deforestation_mapbiomas_importer import DeforestationMapbiomasImporter


@shared_task
def import_deforestation_mapbiomas_task():
    DeforestationMapbiomasImporter().execute()

