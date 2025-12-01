from celery import shared_task
from car_system.tasks.sicar_importer import SicarImporter


@shared_task
def import_sicar_task():
    SicarImporter().execute()

