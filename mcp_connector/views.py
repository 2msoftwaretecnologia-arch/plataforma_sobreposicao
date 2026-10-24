from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

from .exports import build_file, read_token
from .queries import QueryError


def _text(message, status):
    return HttpResponse(message, status=status, content_type='text/plain; charset=utf-8')


@require_GET
def download_file(request, token):
    """Arquivo de um link entregue pelo assistente (ver `exports.file_url`).

    O link é a autorização: assinado, com validade, e gerado para um usuário.
    O arquivo sai com as bases que esse usuário pode ver agora.
    """
    try:
        payload = read_token(token)
    except signing.SignatureExpired:
        return _text('Este link expirou. Peça um novo ao assistente.', 410)
    except signing.BadSignature:
        raise Http404
    user = get_user_model().objects.filter(pk=payload.get('u'), is_active=True).first()
    if user is None:
        raise Http404
    try:
        content, filename, content_type = build_file(user, payload)
    except QueryError as exc:
        return _text(str(exc), 400)
    except PermissionDenied as exc:
        return _text(str(exc) or 'Sem acesso a esta base de dados.', 403)
    response = HttpResponse(content, content_type=content_type)
    disposition = 'inline' if content_type == 'image/png' else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response
