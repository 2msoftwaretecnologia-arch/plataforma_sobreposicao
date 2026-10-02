from celery import shared_task


@shared_task
def run_cross_batch_task(batch_id):
    """Cruzamento em lote dos CARs da tela de Localizações (ver
    `analysis/services/view_services/cross_batch_service.py`)."""
    from analysis.services.view_services.cross_batch_service import run_batch

    run_batch(batch_id)
