from celery import shared_task
from seplan.tasks.Highways_importer import HighwaysImporter



@shared_task
def import_highways_task():
    HighwaysImporter().execute()



