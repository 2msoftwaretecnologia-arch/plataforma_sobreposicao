"""Servidor MCP remoto usado pelo Claude e pelo ChatGPT.

Roda num processo próprio (`python manage.py run_mcp_server`), atrás do nginx
em /mcp. Cada requisição traz um token OAuth emitido pela própria plataforma;
o verificador abaixo o resolve para o usuário, e as ferramentas executam as
consultas de queries.py/exports.py/uploads.py em nome dele, registrando cada
chamada. Mesmo desenho do conector do CRM Agropassos.

As respostas saem por SSE (`json_response=False`) para o assistente receber
o andamento das análises (notificações de progresso) enquanto elas rodam.
"""

import asyncio
import hashlib
import json
import logging
from typing import Annotated, Literal
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from oauth2_provider.models import get_access_token_model
from pydantic import Field

from . import exports, queries, uploads
from .models import McpAuditLog
from .prompts import register_prompts
from .schemas import (
    AnaliseResumo,
    ArquivosAnalise,
    DetalhesBase,
    LinkEnvio,
    ListaAnalises,
    PontoLocalizado,
    PontoSemImovel,
    Relatorio,
    ResultadoEnvio,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    'Análise de sobreposição de imóveis rurais do Tocantins (TerraView Tocantins), em nome do usuário '
    'conectado. A área pode vir pelo número do CAR (analisar_car), por coordenadas digitadas '
    '(analisar_coordenadas: 1 ponto acha o imóvel do SICAR que o contém; 3 ou mais vértices formam o '
    'polígono), pelo conteúdo de um KML, GeoJSON ou WKT (analisar_geometria; para um arquivo de texto anexado '
    'na conversa, passe o texto do arquivo) ou pelo código de uma parcela do SIGEF (analisar_parcela_sigef). '
    'Shapefile (ZIP), KMZ e os PDFs do CAR (demonstrativo, recibo) não passam pela conversa: use link_envio, '
    'mostre o link ao usuário e, quando ele avisar que enviou, chame resultado_envio. '
    'Cada análise cruza a área com todas as bases liberadas para a conta (embargos do IBAMA, PRODES, '
    'MapBiomas, terras indígenas, quilombolas, unidades de conservação, APAs, SICAR, SIGEF, zoneamento, '
    'vegetação etc.), leva de alguns segundos a um minuto, fica no histórico da plataforma e devolve um '
    'analise_id. Uma análise recente da mesma área é reaproveitada sozinha ("reaproveitada": true) quando '
    'nenhuma base mudou desde então; forcar_nova=true refaz. Há limite de análises por minuto e por hora. '
    'Com o analise_id: detalhes_analise (todos os itens e atributos de uma base), relatorio_analise (semáforo, '
    'Reserva Legal, uso do solo, localização e a data de atualização de cada base), mapa_analise (imagem '
    'atual com o imóvel e as sobreposições), imagem_historica (satélite de um ano, ex. 2008, marco do Código '
    'Florestal, ao lado da atual), mapa_uso_solo (classes do MapBiomas no imóvel, 2008 × atual) e '
    'arquivos_analise (PDF do relatório, KML/SHP e PNG). listar_analises mostra o histórico; localizar_ponto '
    'diz o município, os CARs e as parcelas SIGEF de uma coordenada sem fazer análise. '
    'Níveis: "alerta" (embargo, desmatamento recente, terra indígena/quilombola) exige ação; "atencao" '
    'merece conferência; "info" só descreve o lugar. Itens com "residual": true são encostes menores que '
    'limite_residual_ha, quase sempre diferença de desenho entre os mapas. Áreas em hectares. '
    'Ao mostrar ou citar qualquer imagem, informe sempre de onde ela é, com o que vier em fonte_imagem: '
    'satélite e sensor, data da captura, resolução e provedor (ou, no MapBiomas, a coleção e o ano). '
    'Sempre mostre ao usuário os links devolvidos.'
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# As análises só acrescentam um registro ao histórico do próprio usuário.
ANALYSIS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
# Argumentos longos (geometria colada) não vão inteiros para a auditoria.
MAX_AUDIT_CHARS = 1000


def _lookup_token(token):
    close_old_connections()
    try:
        checksum = hashlib.sha256(token.encode('utf-8')).hexdigest()
        access = (
            get_access_token_model().objects
            .select_related('user', 'application')
            .filter(token_checksum=checksum)
            .first()
        )
        if (
            access is None
            or not access.is_valid([settings.MCP_OAUTH_SCOPE])
            or access.user is None
            or not access.user.is_active
        ):
            return None
        return AccessToken(
            token=token,
            client_id=access.application.client_id if access.application else '',
            scopes=access.scope.split(),
            expires_at=int(access.expires.timestamp()),
            subject=str(access.user_id),
        )
    finally:
        close_old_connections()


class PlatformTokenVerifier:
    async def verify_token(self, token):
        return await sync_to_async(_lookup_token)(token)


def _audit_arguments(arguments):
    return {
        key: (f'{value[:MAX_AUDIT_CHARS]}… ({len(value)} caracteres)'
              if isinstance(value, str) and len(value) > MAX_AUDIT_CHARS else value)
        for key, value in arguments.items()
    }


def _execute(user_id, tool_name, query, arguments, progress=None):
    close_old_connections()
    user = None
    audit = _audit_arguments(arguments)
    try:
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            raise queries.QueryError('Conta desativada ou sessão inválida. Reconecte a plataforma no assistente.')
        result = query(user, **arguments, **({'progress': progress} if progress else {}))
        McpAuditLog.objects.create(user=user, tool=tool_name, arguments=audit)
        return result
    except (queries.QueryError, PermissionDenied) as exc:
        message = str(exc) or 'Sua conta não tem acesso a esta base de dados.'
        McpAuditLog.objects.create(user=user, tool=tool_name, arguments=audit, success=False, error=message)
        raise ToolError(message) from None
    except Exception as exc:
        logger.exception('Falha na ferramenta MCP %s', tool_name)
        McpAuditLog.objects.create(user=user, tool=tool_name, arguments=audit, success=False, error=repr(exc))
        raise ToolError('Erro interno na plataforma. Tente novamente mais tarde.') from None
    finally:
        close_old_connections()


def _progress(ctx):
    """Andamento da análise (thread do Django) como notificação de progresso do
    MCP; só é enviado quando o assistente pediu (progressToken)."""
    if ctx is None:
        return None
    loop = asyncio.get_running_loop()

    def report(done, total, message):
        asyncio.run_coroutine_threadsafe(ctx.report_progress(done, total or None, message), loop)

    return queries.ToolProgress(report)


async def _call(tool_name, query, ctx=None, **arguments):
    access = get_access_token()
    user_id = int(access.subject) if access and access.subject else None
    # Fora da thread única do `sync_to_async` padrão: uma análise demorada de
    # um usuário não segura as dos outros.
    return await sync_to_async(_execute, thread_sensitive=False)(user_id, tool_name, query, arguments, _progress(ctx))


def _images(results):
    """Conteúdo de uma ferramenta de imagem: para cada uma, o resumo (com a fonte) e a imagem."""
    content = []
    for png, info in results:
        content += [json.dumps(info, ensure_ascii=False), Image(data=exports.static_map.to_jpeg(png), format='jpeg')]
    return content


def _allowed_hosts(*urls):
    hosts = []
    for url in urls:
        host = urlsplit(url).netloc
        hosts.append(host)
        if host.split(':')[0] in ('localhost', '127.0.0.1'):
            hosts += ['localhost:*', '127.0.0.1:*']
    return list(dict.fromkeys(hosts))


AnaliseId = Annotated[int, Field(description='Número da análise (analise_id) devolvido pelas análises ou por listar_analises.')]
Identificacao = Annotated[str | None, Field(description='Nome ou CAR da área, só para identificar no histórico.')]
ForcarNova = Annotated[bool, Field(description=(
    'true refaz a análise mesmo havendo uma recente da mesma área (o padrão reaproveita quando nenhuma base mudou).'))]


def build_server():
    base_url = settings.MCP_PUBLIC_BASE_URL
    resource_url = settings.MCP_RESOURCE_URL
    server = FastMCP(
        'TerraView Tocantins',
        instructions=INSTRUCTIONS,
        token_verifier=PlatformTokenVerifier(),
        auth=AuthSettings(
            issuer_url=base_url,
            resource_server_url=resource_url,
            required_scopes=[settings.MCP_OAUTH_SCOPE],
            # O django-oauth-toolkit não vincula tokens a um `resource`; todos
            # os tokens que ele emite são para este servidor.
            validate_token_resource=False,
        ),
        host=settings.MCP_SERVER_HOST,
        port=settings.MCP_SERVER_PORT,
        stateless_http=True,
        json_response=False,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_allowed_hosts(base_url, resource_url),
            allowed_origins=[base_url, 'https://claude.ai', 'https://claude.com', 'https://chatgpt.com'],
        ),
    )

    # -----------------------------------------------------------------------
    # Análises
    # -----------------------------------------------------------------------

    @server.tool(annotations=ANALYSIS)
    async def analisar_car(
        numero_car: Annotated[str, Field(description='Número do CAR, ex.: TO-1721000-1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D.')],
        ctx: Context,
        forcar_nova: ForcarNova = False,
    ) -> AnaliseResumo:
        """Cruza o imóvel do CAR (base do SICAR) com todas as bases e devolve as sobreposições.

        A resposta lista as bases com sobreposição (nível, quantidade, área em ha e % do imóvel), as
        bases sem sobreposição, o analise_id e os links para o resultado e o relatório na plataforma.
        """
        return await _call('analisar_car', queries.analyze_car, ctx, car_number=numero_car, forcar_nova=forcar_nova)

    @server.tool(annotations=ANALYSIS)
    async def analisar_coordenadas(
        coordenadas: Annotated[str, Field(description=(
            'Uma coordenada por linha, em graus decimais ("-10.1873, -48.3336") ou graus/min/seg '
            '("10°11\'14,3" S 48°20\'01,0" W"), em qualquer ordem lat/lon. 1 linha = ponto; '
            '3 ou mais = vértices do perímetro, na ordem.'))],
        ctx: Context,
        identificacao: Identificacao = None,
        forcar_nova: ForcarNova = False,
    ) -> AnaliseResumo | PontoSemImovel:
        """Analisa a área formada pelos vértices informados; com um único ponto, analisa o imóvel do SICAR onde ele cai.

        Sem hemisfério, as coordenadas são tratadas como sul/oeste (Tocantins).
        """
        return await _call('analisar_coordenadas', queries.analyze_coordinates, ctx, coordinates=coordenadas,
                           label=identificacao, forcar_nova=forcar_nova)

    @server.tool(annotations=ANALYSIS)
    async def analisar_geometria(
        geometria: Annotated[str, Field(description=(
            'Conteúdo de um arquivo KML, de um GeoJSON (Feature, FeatureCollection ou geometria) ou um WKT, '
            'com o polígono da área em latitude/longitude.'))],
        ctx: Context,
        identificacao: Identificacao = None,
        forcar_nova: ForcarNova = False,
    ) -> AnaliseResumo:
        """Analisa a área desenhada num KML, GeoJSON ou WKT (todos os polígonos viram uma área só).

        Para um KML ou GeoJSON anexado na conversa, envie o texto do arquivo. Shapefile (ZIP) e KMZ
        binário não passam por aqui: use link_envio.
        """
        return await _call('analisar_geometria', queries.analyze_geometry, ctx, geometry_text=geometria,
                           label=identificacao, forcar_nova=forcar_nova)

    @server.tool(annotations=ANALYSIS)
    async def analisar_parcela_sigef(
        codigo_parcela: Annotated[str, Field(description='Código da parcela certificada no SIGEF (INCRA).')],
        ctx: Context,
        forcar_nova: ForcarNova = False,
    ) -> AnaliseResumo:
        """Cruza uma parcela do SIGEF com todas as bases, como a busca por CAR."""
        return await _call('analisar_parcela_sigef', queries.analyze_sigef, ctx, parcel_code=codigo_parcela,
                           forcar_nova=forcar_nova)

    # -----------------------------------------------------------------------
    # Envio de arquivos (shapefile, KMZ, PDF do CAR)
    # -----------------------------------------------------------------------

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                                             openWorldHint=False))
    async def link_envio(
        tipo: Annotated[Literal['area', 'demonstrativo', 'recibo'], Field(description=(
            '"area" = shapefile compactado (.zip), KML/KMZ ou GeoJSON com o perímetro; "demonstrativo" ou '
            '"recibo" = PDF do CAR (a análise usa o CAR do documento e a Reserva Legal declarada).'))] = 'area',
        identificacao: Identificacao = None,
    ) -> LinkEnvio:
        """Link (válido por 1 hora, uso único) para o usuário enviar pela plataforma um arquivo que não passa
        pela conversa. Depois que ele enviar, chame resultado_envio com o código."""
        return await _call('link_envio', uploads.create_upload, kind=tipo, label=identificacao)

    @server.tool(annotations=READ_ONLY)
    async def resultado_envio(
        codigo: Annotated[str, Field(description='Código devolvido por link_envio.')],
    ) -> ResultadoEnvio:
        """Situação de um envio feito pelo link_envio e, quando concluído, o resumo da análise do arquivo."""
        return await _call('resultado_envio', uploads.upload_result, code=codigo)

    # -----------------------------------------------------------------------
    # Consultas
    # -----------------------------------------------------------------------

    @server.tool(annotations=READ_ONLY)
    async def localizar_ponto(
        latitude: Annotated[float, Field(description='Latitude em graus decimais (negativa no sul).')],
        longitude: Annotated[float, Field(description='Longitude em graus decimais (negativa no oeste).')],
    ) -> PontoLocalizado:
        """Município, imóveis do SICAR (CAR, situação, área) e parcelas do SIGEF que contêm o ponto, sem fazer análise."""
        return await _call('localizar_ponto', queries.locate_point, latitude=latitude, longitude=longitude)

    @server.tool(annotations=READ_ONLY)
    async def listar_analises(
        busca: Annotated[str | None, Field(description='Trecho do CAR, da identificação ou do município.')] = None,
        tipo: Annotated[str | None, Field(description=(
            'Filtra pelo tipo: car, shapefile, kml, coordenadas, demonstrativo, recibo ou sigef.'))] = None,
        pagina: Annotated[int, Field(description='Página (20 por página).', ge=1)] = 1,
    ) -> ListaAnalises:
        """Análises do usuário (as feitas pela plataforma e pelo assistente), da mais recente para a mais antiga."""
        return await _call('listar_analises', queries.list_analyses, search=busca, kind=tipo, page=pagina)

    @server.tool(annotations=READ_ONLY)
    async def detalhes_analise(
        analise_id: AnaliseId,
        base: Annotated[str | None, Field(description=(
            'Nome (ou trecho do nome) de uma base, ex.: "Embargos", "Sigef", "Zoneamento". Vazio = resumo da análise.'))] = None,
    ) -> AnaliseResumo | DetalhesBase:
        """Resumo de uma análise já feita ou, com `base`, todos os itens dessa base com os atributos (proprietário, ano, situação...)."""
        return await _call('detalhes_analise', queries.analysis_details, analise_id=analise_id, base=base)

    @server.tool(annotations=READ_ONLY)
    async def relatorio_analise(analise_id: AnaliseId) -> Relatorio:
        """Conteúdo do relatório da análise, em linguagem simples.

        Traz o veredito, as perguntas do semáforo (embargo, desmatamento, terra indígena, área protegida,
        Reserva Legal, APP) com resposta e explicação, as bases com ocorrência e o que significam, a
        vegetação natural, o comparativo de uso do solo do MapBiomas (2008 × ano atual), a coordenada
        central, a data de atualização de cada base e os links do relatório (para imprimir e em PDF).
        Use para redigir relatórios e pareceres.
        """
        return await _call('relatorio_analise', queries.analysis_report, analise_id=analise_id)

    @server.tool(annotations=READ_ONLY)
    async def arquivos_analise(analise_id: AnaliseId) -> ArquivosAnalise:
        """Links para baixar os arquivos da análise: o relatório em PDF, KML e SHP do imóvel, de cada base com
        sobreposição e de todas as sobreposições juntas (KML com uma pasta colorida por base), e o PNG do mapa."""
        return await _call('arquivos_analise', exports.download_links, analise_id=analise_id)

    # -----------------------------------------------------------------------
    # Imagens
    # -----------------------------------------------------------------------

    @server.tool(annotations=READ_ONLY, structured_output=False)
    async def mapa_analise(
        analise_id: AnaliseId,
        base: Annotated[str | None, Field(description=(
            'Vazio = bases de alerta e atenção; "todas" = todas as bases com sobreposição (menos zoneamento, '
            'vegetação e município); ou o nome de uma base para ver os itens dela, cada um com uma cor.'))] = None,
        fundo: Annotated[Literal['satelite', 'mapa'], Field(description=(
            '"satelite" (imagem atual da Esri, com o satélite e a data da captura) ou "mapa" (mapa topográfico).'))] = 'satelite',
    ) -> list:
        """Imagem do mapa (print) com o contorno do imóvel e as sobreposições, legenda, escala e a fonte da imagem.

        Devolve a imagem, a fonte_imagem (satélite, data da captura, resolução, provedor) e um link para
        baixar o PNG em alta resolução.
        """
        png, info = await _call('mapa_analise', exports.analysis_map, analise_id=analise_id, base=base, fundo=fundo)
        return _images([(png, info)])

    @server.tool(annotations=READ_ONLY, structured_output=False)
    async def imagem_historica(
        analise_id: AnaliseId,
        ano: Annotated[int, Field(description=(
            'Ano da imagem: 1984 a 2012 (Landsat 4/5/7, 30 m) ou de 2014 em diante (Esri Wayback, alta resolução). '
            'Padrão: 2008, marco do Código Florestal (22/07/2008).'))] = 2008,
        comparar_com_atual: Annotated[bool, Field(description='Também devolve a imagem atual, para comparar.')] = True,
        composicao: Annotated[Literal['natural', 'falsa_cor', 'infravermelho'], Field(description=(
            'Só para o Landsat: "natural" (cor real), "falsa_cor" (vegetação em vermelho) ou "infravermelho" '
            '(realça solo exposto e desmate).'))] = 'natural',
        cena: Annotated[str | None, Field(description=(
            'Id de outra cena Landsat (de fonte_imagem.outras_cenas_do_ano), se a escolhida tiver nuvem sobre o imóvel.'))] = None,
        base: Annotated[str | None, Field(description=(
            'Sobreposições desenhadas por cima: vazio = só o contorno do imóvel; "alertas"; "todas"; ou o nome de uma base.'))] = None,
    ) -> list:
        """Imagem de satélite do imóvel num ano passado (padrão 2008) e, ao lado, a atual.

        Para ver se a vegetação foi retirada antes ou depois do marco do Código Florestal. Cada imagem vem
        com a fonte_imagem: satélite e sensor, data da captura, resolução, nuvens e provedor; o Landsat
        escolhe a cena com menos nuvens do ano (perto de julho) e lista as outras.
        """
        results = await _call('imagem_historica', exports.historical_images, analise_id=analise_id, ano=ano,
                              composicao=composicao, cena=cena, base=base, comparar_com_atual=comparar_com_atual)
        return _images(results)

    @server.tool(annotations=READ_ONLY, structured_output=False)
    async def mapa_uso_solo(
        analise_id: AnaliseId,
        ano: Annotated[int | None, Field(description='Ano do MapBiomas (1985 em diante). Vazio = o mais recente.')] = None,
        comparar_com_2008: Annotated[bool, Field(description='Também devolve o mapa de 2008, para comparar.')] = True,
    ) -> list:
        """Mapa das classes de cobertura e uso da terra do MapBiomas no imóvel (vegetação, pastagem, lavoura...).

        A legenda e a fonte_imagem trazem a parte de cada classe dentro do imóvel (% e ha, estimados pelos
        pixels de 30 m). Por padrão vem o de 2008 e o mais recente, para comparar.
        """
        results = await _call('mapa_uso_solo', exports.land_use_maps, analise_id=analise_id, ano=ano,
                              comparar_com_2008=comparar_com_2008)
        return _images(results)

    register_prompts(server)
    return server
