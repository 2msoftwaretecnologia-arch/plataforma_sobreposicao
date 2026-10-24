from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from . import uploads
from .exports import build_file, read_token
from .models import McpUpload
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
    disposition = 'inline' if content_type in ('image/png', 'application/pdf') else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response


@require_http_methods(['GET', 'POST'])
def upload_page(request, code):
    """Página do link de envio (ver `uploads`): recebe o arquivo e faz a análise."""
    upload = uploads.open_upload(code)
    if upload is None:
        done = McpUpload.objects.filter(code=code, status=McpUpload.Status.DONE).first()
        return render(request, 'mcp_connector/enviar.html', {'upload': done}, status=200 if done else 410)
    accept, description = uploads.ACCEPTS[upload.kind]
    context = {'upload': upload, 'aceita': accept, 'descricao': description}
    if request.method == 'POST':
        file_obj = request.FILES.get('arquivo')
        if file_obj is None:
            context['erro'] = 'Escolha o arquivo antes de enviar.'
        else:
            try:
                upload = uploads.process_upload(upload, file_obj, request.POST.get('car', '').strip())
            except QueryError as exc:
                context['erro'] = str(exc)
            else:
                context['upload'] = upload
                if upload.status == McpUpload.Status.ERROR:
                    context['erro'] = upload.error
    return render(request, 'mcp_connector/enviar.html', context)
