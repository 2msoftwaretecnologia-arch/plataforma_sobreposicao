from celery import shared_task
from gov.tasks.sigef_importer import SigefImporter
from gov.tasks.ruralsettlement_importer import RuralsettlementImporter

@shared_task
def import_sigef_task():
    SigefImporter().execute()

@shared_task
def import_ruralsettlement_task():
    RuralsettlementImporter().execute()

