from celery import shared_task
from naturatins.tasks.quilombolas_importer import QuilombolasImporter
from naturatins.tasks.paths_importer import PathsImporter
from naturatins.tasks.municipal_boundaries_importer import MunicipalBoundariesImporter
from naturatins.tasks.conservation_units_importer import ConservationUnitsImporter


@shared_task
def import_quilombolas_task():
    QuilombolasImporter().execute()


@shared_task
def import_paths_task():
    PathsImporter().execute()


@shared_task
def import_municipal_boundaries_task():
    MunicipalBoundariesImporter().execute()


@shared_task
def import_conservation_units_task():
    ConservationUnitsImporter().execute()

