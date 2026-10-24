import uvicorn
from django.conf import settings
from django.core.management.base import BaseCommand

from mcp_connector.server import build_server


class Command(BaseCommand):
    help = 'Inicia o servidor MCP (Streamable HTTP) usado pelo Claude e pelo ChatGPT.'

    def handle(self, *args, **options):
        app = build_server().streamable_http_app()
        self.stdout.write(
            f'Servidor MCP em {settings.MCP_SERVER_HOST}:{settings.MCP_SERVER_PORT} '
            f'(público: {settings.MCP_RESOURCE_URL})'
        )
        uvicorn.run(
            app,
            host=settings.MCP_SERVER_HOST,
            port=settings.MCP_SERVER_PORT,
            proxy_headers=True,
            forwarded_allow_ips='*',
            log_level='info',
        )
