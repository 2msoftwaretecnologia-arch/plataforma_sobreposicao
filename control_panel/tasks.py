from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True)
def process_layer_task(self, modelo, user_id=None):
    """Executa o Importer de uma camada (`LAYER_REGISTRY`) em background.

    Roda no worker Celery em vez do processo web: importar uma base grande
    (SICAR, MapBiomas etc.) pode levar minutos, e antes disso travava um dos
    processos uwsgi pelo tempo todo do import."""
    from django.contrib.auth import get_user_model

    from .layer_registry import LAYER_REGISTRY

    entry = LAYER_REGISTRY.get(modelo)
    if entry is None:
        logger.error("Base '%s' não encontrada no LAYER_REGISTRY.", modelo)
        return {"ok": False, "error": f"Base '{modelo}' não encontrada."}

    user = None
    if user_id is not None:
        User = get_user_model()
        user = User.objects.filter(pk=user_id).first()

    importer_cls = entry["importer"]
    try:
        total = importer_cls(user=user).execute()
    except Exception as exc:
        logger.exception("Falha ao processar base '%s'.", modelo)
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "total": total}
