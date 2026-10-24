"""Partes do OAuth que o django-oauth-toolkit não traz e os assistentes exigem.

- Metadados do servidor de autorização (RFC 8414), lidos pelo Claude e pelo
  ChatGPT para descobrir os endpoints.
- Registro dinâmico de cliente (RFC 7591), restrito aos callbacks dos assistentes.
- Tela de autorização com a identidade visual da plataforma.

Mesmo desenho do conector do CRM Agropassos (`crm_Agropassos/mcp_connector`).
"""

import json
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from oauth2_provider.generators import generate_client_secret
from oauth2_provider.models import get_application_model
from oauth2_provider.views import AuthorizationView
from pydantic import AnyHttpUrl

SUPPORTED_GRANT_TYPES = ('authorization_code', 'refresh_token')
# "none" é o cliente público com PKCE (Claude). Os outros dois atendem quem
# prefere se registrar com segredo, como o ChatGPT pode fazer; o PKCE continua
# obrigatório para todos.
SUPPORTED_AUTH_METHODS = ('none', 'client_secret_post', 'client_secret_basic')


def _absolute(route_name):
    return settings.MCP_PUBLIC_BASE_URL + reverse(route_name)


@require_GET
def authorization_server_metadata(request):
    return JsonResponse({
        # Mesma normalização que o SDK do MCP aplica ao anunciar o servidor de
        # autorização (barra final num domínio sem caminho); clientes OAuth
        # comparam os dois valores literalmente.
        'issuer': str(AnyHttpUrl(settings.MCP_PUBLIC_BASE_URL)),
        'authorization_endpoint': _absolute('oauth2_provider:authorize'),
        'token_endpoint': _absolute('oauth2_provider:token'),
        'revocation_endpoint': _absolute('oauth2_provider:revoke-token'),
        'registration_endpoint': _absolute('oauth2_provider:register-client'),
        'response_types_supported': ['code'],
        'grant_types_supported': list(SUPPORTED_GRANT_TYPES),
        'code_challenge_methods_supported': ['S256'],
        'token_endpoint_auth_methods_supported': list(SUPPORTED_AUTH_METHODS),
        'scopes_supported': [settings.MCP_OAUTH_SCOPE],
    })


def _redirect_allowed(uri):
    if not isinstance(uri, str) or any(char.isspace() for char in uri):
        return False
    for allowed in settings.MCP_ALLOWED_REDIRECT_URIS:
        if allowed.endswith('*'):
            prefix = allowed[:-1]
            # O id vem depois do prefixo, sem query, fragmento ou outro nível.
            rest = uri[len(prefix):] if uri.startswith(prefix) else ''
            if rest and not any(char in rest for char in '/?#'):
                return True
        elif uri == allowed:
            return True
    if not settings.MCP_ALLOW_LOOPBACK_REDIRECTS:
        return False
    parts = urlsplit(uri)
    return parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1')


def _registration_error(description, error='invalid_client_metadata'):
    return JsonResponse({'error': error, 'error_description': description}, status=400)


@csrf_exempt
@require_POST
def register_client(request):
    try:
        metadata = json.loads(request.body or b'{}')
    except ValueError:
        return _registration_error('O corpo da requisição deve ser JSON.')
    if not isinstance(metadata, dict):
        return _registration_error('O corpo da requisição deve ser um objeto JSON.')

    redirect_uris = metadata.get('redirect_uris')
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return _registration_error('Informe ao menos um redirect_uri.', 'invalid_redirect_uri')
    if not all(_redirect_allowed(uri) for uri in redirect_uris):
        return _registration_error('redirect_uri não autorizado.', 'invalid_redirect_uri')

    auth_method = metadata.get('token_endpoint_auth_method', 'none')
    if auth_method not in SUPPORTED_AUTH_METHODS:
        return _registration_error('token_endpoint_auth_method não suportado.')
    grant_types = metadata.get('grant_types') or ['authorization_code', 'refresh_token']
    if not isinstance(grant_types, list) or not set(grant_types) <= set(SUPPORTED_GRANT_TYPES):
        return _registration_error('grant_types não suportado.')

    application_model = get_application_model()
    client_name = str(metadata.get('client_name') or 'Cliente MCP')[:255]
    confidential = auth_method != 'none'
    # O segredo é gravado com hash; esta resposta é a única vez em que aparece.
    client_secret = generate_client_secret() if confidential else ''
    application = application_model.objects.create(
        name=client_name,
        client_type=application_model.CLIENT_CONFIDENTIAL if confidential else application_model.CLIENT_PUBLIC,
        authorization_grant_type=application_model.GRANT_AUTHORIZATION_CODE,
        redirect_uris=' '.join(redirect_uris),
        skip_authorization=False,
        **({'client_secret': client_secret} if confidential else {}),
    )
    issued_at = int(timezone.now().timestamp())
    response = {
        'client_id': application.client_id,
        'client_id_issued_at': issued_at,
        'client_name': client_name,
        'redirect_uris': redirect_uris,
        'grant_types': grant_types,
        'response_types': ['code'],
        'token_endpoint_auth_method': auth_method,
        'scope': settings.MCP_OAUTH_SCOPE,
    }
    if confidential:
        response.update(client_secret=client_secret, client_secret_expires_at=0)
    return JsonResponse(response, status=201)


class ConnectorAuthorizationView(AuthorizationView):
    """Login da plataforma + "Permitir acesso?". Qualquer conta ativa pode
    conectar: as ferramentas já respeitam as bases liberadas para ela."""
    template_name = 'oauth2_provider/authorize.html'
