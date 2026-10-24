"""Token de acesso para testar o servidor MCP localmente, sem o fluxo OAuth.

Só funciona com DEBUG ligado. O token pertence a um usuário real do banco e
vê exatamente o que esse usuário vê na plataforma.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model

DEV_APPLICATION_NAME = 'Desenvolvimento local (mcp_dev_token)'


class Command(BaseCommand):
    help = 'Gera um token de acesso ao servidor MCP para um usuário (somente desenvolvimento).'

    def add_arguments(self, parser):
        parser.add_argument('username', help='Usuário da plataforma dono do token.')
        parser.add_argument('--days', type=int, default=7, help='Validade em dias (padrão: 7).')

    def handle(self, *args, username, days, **options):
        if not settings.DEBUG:
            raise CommandError('Comando disponível somente em desenvolvimento (DEBUG=True).')
        user = get_user_model().objects.filter(username=username, is_active=True).first()
        if user is None:
            raise CommandError(f'Usuário ativo "{username}" não encontrado.')

        application_model = get_application_model()
        application, _ = application_model.objects.get_or_create(
            name=DEV_APPLICATION_NAME,
            defaults={
                'client_type': application_model.CLIENT_PUBLIC,
                'authorization_grant_type': application_model.GRANT_AUTHORIZATION_CODE,
                'redirect_uris': 'http://localhost/callback',
            },
        )
        token = secrets.token_urlsafe(32)
        get_access_token_model().objects.create(
            user=user,
            application=application,
            token=token,
            scope=settings.MCP_OAUTH_SCOPE,
            expires=timezone.now() + timedelta(days=days),
        )

        self.stdout.write(self.style.SUCCESS(f'Token de {username} válido por {days} dia(s):'))
        self.stdout.write(token)
        self.stdout.write('\nPara usar no Claude Code:')
        self.stdout.write(
            f'claude mcp add --transport http sobreposicao-dev {settings.MCP_RESOURCE_URL} '
            f'--header "Authorization: Bearer {token}"'
        )
