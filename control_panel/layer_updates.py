"""Quando cada base foi atualizada pela última vez.

Cada importação concluída grava um `LayerUpdate` (ver
`BulkShapefileImporter.execute`). Bases importadas antes desse registro
existir caem na data do arquivo enviado no painel; as que vêm de API e nunca
foram reimportadas desde então ficam sem data.
"""
import os
from datetime import datetime, timezone

from .bases_config import BASES_CONFIG
from .models import LayerUpdate
from .utils import get_file_management


def record_layer_update(modelo, total=0):
    LayerUpdate.objects.create(modelo=modelo, total=total or 0)


def _file_date(file_mgmt, field_name):
    file_field = getattr(file_mgmt, field_name, None) if file_mgmt and field_name else None
    if not file_field or not file_field.name:
        return None
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_field.path), tz=timezone.utc)
    except (OSError, ValueError, NotImplementedError):
        return None


def layer_update_dates():
    """{modelo: (data da última atualização ou None, de onde veio a data)}."""
    recorded = {
        u.modelo: u.finished_at
        for u in LayerUpdate.objects.order_by('modelo', '-finished_at').distinct('modelo')
    }
    file_mgmt = None
    dates = {}
    for base in BASES_CONFIG:
        modelo = base['modelo']
        if modelo in recorded:
            dates[modelo] = (recorded[modelo], 'importacao')
            continue
        if file_mgmt is None:
            file_mgmt = get_file_management() or False
        file_date = _file_date(file_mgmt, base.get('arquivo_upload'))
        dates[modelo] = (file_date, 'arquivo') if file_date else (None, None)
    return dates


def latest_layer_update():
    """Data da atualização mais recente entre todas as bases (ou None)."""
    known = [date for date, _ in layer_update_dates().values() if date]
    return max(known) if known else None
