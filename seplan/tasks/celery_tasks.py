from celery import shared_task
from seplan.tasks.Highways_importer import HighwaysImporter
from seplan.tasks.ipuca_importer import IpucaImporter



@shared_task
def import_highways_task():
    HighwaysImporter().execute()



@shared_task
def import_ipuca_task():
    IpucaImporter().execute()
