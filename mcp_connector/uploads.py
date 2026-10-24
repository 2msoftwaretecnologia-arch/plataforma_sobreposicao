"""Envio de arquivo pelo link entregue pelo assistente (ver `McpUpload`).

O assistente pede o link (`link_envio`), o usuário abre e envia o shapefile,
KML/KMZ, GeoJSON ou o PDF do CAR na página `conector/enviar/<código>/`, que
faz a análise como a tela faz e a grava no histórico; o assistente lê o
resultado pelo código (`resultado_envio`). O link vale
`MCP_UPLOAD_LINK_MAX_AGE`, serve para um arquivo só e, como os de download,
abre sem login: o código é a autorização.
"""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from . import queries
from .models import McpAuditLog, McpUpload
from .queries import QueryError

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 150 * 1024 * 1024
ACCEPTS = {
    McpUpload.Kind.AREA: ('.zip,.kml,.kmz,.geojson,.json', 'shapefile compactado (.zip), KML/KMZ ou GeoJSON'),
    McpUpload.Kind.DEMONSTRATIVO: ('.pdf', 'PDF do Demonstrativo do CAR'),
    McpUpload.Kind.RECIBO: ('.pdf', 'PDF do Recibo de inscrição do CAR'),
}
OPEN_STATUSES = (McpUpload.Status.PENDING, McpUpload.Status.ERROR)


def _minutes():
    return settings.MCP_UPLOAD_LINK_MAX_AGE // 60


def expired(upload):
    return timezone.now() > upload.created_at + timedelta(seconds=settings.MCP_UPLOAD_LINK_MAX_AGE)


def create_upload(user, kind, label=None):
    if kind not in McpUpload.Kind.values:
        raise QueryError(f'Tipo inválido. Use um destes: {", ".join(McpUpload.Kind.values)}.')
    upload = McpUpload.objects.create(
        code=secrets.token_urlsafe(16), user=user, kind=kind, label=(label or '').strip()[:100],
    )
    return {
        'codigo': upload.code,
        'link_envio': queries.public_url(reverse('mcp_connector:enviar', args=[upload.code])),
        'aceita': ACCEPTS[kind][1],
        'validade': f'O link vale {_minutes()} minutos, serve para um arquivo e abre sem login; '
                    'não o repasse a quem não deve fazer análises na sua conta.',
        'proximo_passo': 'Mostre o link ao usuário. Quando ele disser que enviou, chame resultado_envio com este código.',
    }


def open_upload(code):
    """Envio que ainda aceita arquivo, ou None (não existe, expirou ou já foi usado)."""
    upload = McpUpload.objects.select_related('user').filter(code=code).first()
    if upload is None or upload.status not in OPEN_STATUSES or expired(upload) or not upload.user.is_active:
        return None
    return upload


def process_upload(upload, file_obj, car_input=''):
    """Analisa o arquivo enviado e grava o resultado no envio."""
    claimed = McpUpload.objects.filter(pk=upload.pk, status__in=OPEN_STATUSES).update(
        status=McpUpload.Status.PROCESSING)
    if not claimed:
        raise QueryError('Este link já está sendo usado em outra aba ou já recebeu o arquivo.')
    upload.filename = (file_obj.name or '')[:255]
    internal_error = None
    try:
        if file_obj.size > MAX_UPLOAD_BYTES:
            raise QueryError(f'O arquivo passa de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')
        if upload.kind == McpUpload.Kind.AREA:
            summary = queries.analyze_area_file(upload.user, file_obj, upload.label)
        else:
            summary = queries.analyze_document(upload.user, file_obj, upload.kind, car_input or upload.label)
        upload.status, upload.error, upload.analysis_id = McpUpload.Status.DONE, '', summary['analise_id']
    except (QueryError, PermissionDenied) as exc:
        upload.status, upload.error = McpUpload.Status.ERROR, str(exc) or 'Sua conta não tem acesso a esta base.'
    except Exception as exc:
        logger.exception('Falha ao analisar o arquivo do envio %s', upload.pk)
        upload.status, upload.error = McpUpload.Status.ERROR, 'Erro interno na plataforma. Tente de novo mais tarde.'
        internal_error = repr(exc)
    upload.finished_at = timezone.now()
    upload.save()
    McpAuditLog.objects.create(
        user=upload.user, tool='envio_por_link', success=upload.status == McpUpload.Status.DONE,
        error=internal_error or upload.error,
        arguments={'codigo': upload.code, 'tipo': upload.kind, 'arquivo': upload.filename},
    )
    return upload


def upload_result(user, code):
    """Situação do envio e, quando concluído, o resumo da análise."""
    upload = McpUpload.objects.filter(code=(code or '').strip(), user=user).first()
    if upload is None:
        raise QueryError('Código de envio não encontrado. Peça um novo link com link_envio.')
    result = {'codigo': upload.code, 'tipo': upload.get_kind_display(), 'arquivo': upload.filename or None}
    if upload.status == McpUpload.Status.DONE and upload.analysis_id:
        historico, data = queries.load_analysis(user, upload.analysis_id)
        return {**result, 'situacao': 'concluido', 'analise': queries.analysis_summary(historico, data)}
    if upload.status == McpUpload.Status.PROCESSING:
        return {**result, 'situacao': 'processando', 'mensagem': 'O arquivo chegou e a análise está em andamento.'}
    if expired(upload):
        return {**result, 'situacao': 'expirado', 'mensagem': 'O link venceu sem receber o arquivo. Peça um novo com link_envio.'}
    if upload.status == McpUpload.Status.ERROR:
        return {**result, 'situacao': 'erro', 'mensagem': f'{upload.error} O usuário pode tentar de novo pelo mesmo link.'}
    return {**result, 'situacao': 'aguardando', 'mensagem': 'O usuário ainda não enviou o arquivo pelo link.'}
