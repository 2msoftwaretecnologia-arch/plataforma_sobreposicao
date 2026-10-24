"""O que cada ferramenta do conector faz, em nome do usuário conectado.

As análises passam pelo mesmo motor da tela (`SearchAll`, `SearchForCar`,
`SearchForSigef`) e ficam gravadas no histórico do usuário (`SearchHistory`),
como as feitas pela plataforma: o id do histórico é o `analise_id` que as
demais ferramentas recebem. As respostas trazem só números e textos; as
geometrias saem por link (KML/SHP) ou na imagem do mapa (`static_map`).
"""
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import shapely
from django.conf import settings
from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from shapely import wkt as shapely_wkt
from shapely.errors import ShapelyError
from shapely.geometry import shape
from shapely.ops import unary_union

from analysis.models import SearchHistory
from analysis.services.analyze_coordinates.search_all import SearchAll
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.analyze_coordinates.search_for_sigef import SearchForSigef
from analysis.services.view_services.analysis_progress import AnalysisProgress
from analysis.services.view_services.base_export_service import SKIPPED_KEYS
from analysis.services.view_services.bases_3d import cars_at_point
from analysis.services.view_services.coordinates_input_service import (
    CoordinatesInputError,
    build_polygon,
    parse_vertices,
)
from analysis.services.view_services.cross_batch_service import _is_neutral
from analysis.services.view_services.kml_upload_service import KmlUploadError, KmlUploadService
from analysis.services.view_services.kmz_points_service import locate_municipalities, locate_sigef
from analysis.services.view_services.report_service import (
    NIVEL_ORDEM,
    base_guide,
    build_report_context,
    limite_residual,
)
from analysis.services.view_services.zip_upload_service import ZipUploadService
from analysis.validators import validate_car_number
from car_system.models import SicarRecord
from control_panel.access_service import denied_layers, filter_result, require_layer
from control_panel.bases_config import BASES_CONFIG
from control_panel.layer_updates import latest_layer_update, layer_update_dates
from doc_extractor.services.parsers.constants import TypeDocument
from doc_extractor.services.parsers.context.extract_data_context import DocumentDataContext
from doc_extractor.services.parsers.factory.documents_parser_factory import DocumentsParserFactory
from doc_extractor.services.parsers.implement.extract_text.extract_pdf_plumber import ExtractDocumentPdfPlumber
from kernel.utils import calculate_area_ha, extract_geometry, locate_city_state

from . import limits

LOCAL_TZ = ZoneInfo('America/Sao_Paulo')
# Itens listados por base no resumo da análise (o total sempre vem).
MAX_SUMMARY_ITEMS = 25
# Itens listados em `detalhes_analise` para uma base.
MAX_DETAIL_ITEMS = 300
# Textos de atributos acima disso são cortados (descrições longas de embargos etc.).
MAX_ATTRIBUTE_CHARS = 300
# Geometria colada na conversa (KML, GeoJSON, WKT).
MAX_GEOMETRY_CHARS = 5_000_000
# Cada análise consulta todas as bases; áreas maiores que isso (um município
# inteiro) travariam o banco do site.
MAX_AREA_HA = 300_000
HISTORY_PAGE_SIZE = 20
# Análises de área desenhada: candidatas a reaproveitar, achadas pela área
# (±1 %) e conferidas pela geometria.
GEOMETRY_SEARCH_TYPES = (
    SearchHistory.SearchType.KML, SearchHistory.SearchType.COORDENADAS, SearchHistory.SearchType.SHAPEFILE,
)
REUSE_AREA_TOLERANCE = 0.01
MAX_REUSE_CANDIDATES = 5
DOCUMENTS = {
    'demonstrativo': (TypeDocument.STATEMENT, SearchHistory.SearchType.DEMONSTRATIVO),
    'recibo': (TypeDocument.RECEIPT, SearchHistory.SearchType.RECIBO),
}

VEREDITOS = {
    'alerta': 'Há pontos de alerta',
    'atencao': 'Há pontos para conferir',
    'ok': 'Nenhum problema encontrado',
}


class QueryError(Exception):
    """Erro com mensagem para o usuário: vira o erro da ferramenta."""


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def public_url(path):
    return settings.MCP_PUBLIC_BASE_URL + path


def analysis_links(analise_id):
    return {
        'resultado_na_plataforma': public_url(reverse('historico_detalhe', args=[analise_id])),
        'relatorio_para_imprimir': public_url(f"{reverse('report_print')}?historico={analise_id}"),
    }


def _num(value, digits=4):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _local_time(value):
    return value.astimezone(LOCAL_TZ).strftime('%d/%m/%Y %H:%M')


def item_attributes(item):
    """Colunas do item da base (as mesmas que vão para o KML/SHP), sem geometria."""
    attributes = {}
    for key, value in item.items():
        if key in SKIPPED_KEYS or key in ('item_info', 'area') or value in (None, ''):
            continue
        if isinstance(value, str):
            attributes[key] = value[:MAX_ATTRIBUTE_CHARS]
        elif isinstance(value, (int, float, bool)):
            attributes[key] = value
    return attributes


def find_base(resultado, name):
    """Base do resultado pelo nome completo ou por um trecho dele ("embargos", "sigef")."""
    bases = (resultado or {}).get('resultados_por_base') or []
    wanted = (name or '').strip().lower()
    exact = [b for b in bases if (b.get('nome_base') or '').lower() == wanted]
    if exact:
        return exact[0]
    partial = [b for b in bases if wanted and wanted in (b.get('nome_base') or '').lower()]
    if len(partial) == 1:
        return partial[0]
    names = ', '.join(b.get('nome_base') or '' for b in (partial or bases))
    if partial:
        raise QueryError(f'"{name}" corresponde a mais de uma base: {names}. Use o nome completo.')
    raise QueryError(f'Base "{name}" não encontrada nesta análise. Bases da análise: {names}.')


def _locate(user, wkt):
    """Município e UF da área (como na tela); vazio sem a base de municípios."""
    try:
        require_layer('MunicipalBoundaries', user)
        return locate_city_state(wkt)
    except Exception:
        return None, None


def load_analysis(user, analise_id):
    """Análise do histórico do próprio usuário, filtrada pelas bases liberadas hoje."""
    try:
        pk = int(analise_id)
    except (TypeError, ValueError):
        raise QueryError('analise_id deve ser o número da análise (veja listar_analises).') from None
    historico = SearchHistory.objects.filter(pk=pk, user=user).first()
    if historico is None:
        raise QueryError(f'Análise {pk} não encontrada no seu histórico. Use listar_analises para ver as suas.')
    data = dict(historico.result_data or {})
    if historico.search_type == SearchHistory.SearchType.SIGEF:
        data['source_model'] = 'Sigef'
    return historico, filter_result(data, user)


def _require_result(historico, data):
    if not data.get('sucesso'):
        raise QueryError(f"A análise {historico.pk} terminou com erro: {data.get('erro') or 'sem detalhes'}.")
    if not (data.get('resultado') or {}).get('resultados_por_base'):
        raise QueryError(f'A análise {historico.pk} não tem cruzamento com as bases (sem área analisada).')


# ---------------------------------------------------------------------------
# Resumo de uma análise
# ---------------------------------------------------------------------------

def analysis_summary(historico, data):
    """Resumo compacto do resultado, ordenado do mais grave para o informativo.

    Itens "sem unidade" das bases de UCs e APAs (que cobrem o estado todo)
    não contam como sobreposição, como no cruzamento em lote.
    """
    resultado = data.get('resultado') or {}
    tamanho = _num(resultado.get('tamanho_area')) or 0
    limite = limite_residual(tamanho)
    com_sobreposicao, sem_sobreposicao = [], []
    for base in resultado.get('resultados_por_base') or []:
        nome = base.get('nome_base') or ''
        reais = [item for item in base.get('areas_encontradas') or [] if not _is_neutral(item)]
        if not reais:
            sem_sobreposicao.append(nome)
            continue
        total = sum(_num(item.get('area')) or 0 for item in reais)
        itens = []
        for item in reais[:MAX_SUMMARY_ITEMS]:
            area = _num(item.get('area'))
            entry = {'descricao': item.get('item_info') or '', 'area_ha': area}
            if (area or 0) < limite:
                entry['residual'] = True
            itens.append(entry)
        entry = {
            'base': nome,
            'nivel': base_guide(nome)['nivel'],
            'quantidade': len(reais),
            'area_ha': round(total, 4),
            'percentual_do_imovel': round(min(total / tamanho * 100, 100), 2) if tamanho else None,
            'itens': itens,
        }
        if len(reais) > MAX_SUMMARY_ITEMS:
            entry['itens_nao_listados'] = len(reais) - MAX_SUMMARY_ITEMS
        com_sobreposicao.append(entry)
    com_sobreposicao.sort(key=lambda b: (NIVEL_ORDEM[b['nivel']], -b['area_ha']))

    summary = {
        'analise_id': historico.pk,
        'data': _local_time(historico.created_at),
        'tipo': historico.get_search_type_display(),
        'car_ou_identificacao': data.get('car_input') or None,
        'municipio': data.get('municipio') or None,
        'uf': data.get('uf') or None,
        'area_imovel_ha': tamanho,
        'total_sobreposicoes': sum(b['quantidade'] for b in com_sobreposicao),
        'bases_com_sobreposicao': com_sobreposicao,
        'bases_sem_sobreposicao': sem_sobreposicao,
        'limite_residual_ha': round(limite, 4),
        'links': analysis_links(historico.pk),
    }
    if data.get('aviso'):
        summary['aviso'] = data['aviso']
    return summary


def _finish(user, data, search_type):
    historico = SearchHistory.record(user, data, search_type)
    return analysis_summary(historico, data)


def _run(owner, engine, /, *args, **kwargs):
    """Roda o motor da análise dentro dos limites de uso (ver `limits`)."""
    try:
        with limits.analysis_slot(owner.pk):
            return engine(*args, **kwargs)
    except limits.LimitExceeded as exc:
        raise QueryError(str(exc)) from None


class ToolProgress(AnalysisProgress):
    """Andamento da análise repassado ao assistente (notificações de progresso
    do MCP) em vez do cache da tela: `report(feitas, total, mensagem)`."""

    def __init__(self, report):
        super().__init__()
        self._report = report
        self._last = None

    def __bool__(self):
        return True

    def _save(self):
        state = self.state
        message = state.get('stage') or ''
        if state.get('current') and state.get('stage') == 'Consultando as bases':
            message = f"Consultando as bases: {state['current']}"
        update = (state.get('done') or 0, state.get('total') or 0, message)
        if update != self._last:
            self._last = update
            self._report(*update)


# ---------------------------------------------------------------------------
# Reaproveitamento de análises recentes
# ---------------------------------------------------------------------------

def _reuse_since():
    """Desde quando uma análise ainda vale: dentro de `MCP_REUSE_DAYS` e depois
    da última atualização de qualquer base. None = não reaproveitar."""
    if settings.MCP_REUSE_DAYS <= 0:
        return None
    since = timezone.now() - timedelta(days=settings.MCP_REUSE_DAYS)
    latest = latest_layer_update()
    return max(since, latest) if latest else since


def _reused_summary(user, historico, aviso=None):
    try:
        historico, data = load_analysis(user, historico.pk)
    except (QueryError, PermissionDenied):
        return None
    if not data.get('sucesso') or not (data.get('resultado') or {}).get('resultados_por_base'):
        return None
    summary = analysis_summary(historico, data)
    summary['reaproveitada'] = True
    note = (f"Análise nº {historico.pk} de {summary['data']} reaproveitada: nenhuma base foi atualizada desde "
            'então, então o resultado seria o mesmo. Para refazer mesmo assim, use forcar_nova=true.')
    summary['aviso'] = ' '.join(p for p in (aviso, summary.get('aviso'), note) if p)
    return summary


def find_reusable(user, search_type, code, aviso=None):
    """Análise recente do mesmo CAR ou parcela (`code`), já como resumo."""
    since = _reuse_since()
    if since is None:
        return None
    historico = (
        SearchHistory.objects
        .filter(user=user, search_type=search_type, car_input__iexact=code, sucesso=True, created_at__gt=since)
        .only('pk').first()
    )
    return _reused_summary(user, historico, aviso) if historico else None


def _same_area(a, b):
    try:
        return a.symmetric_difference(b).area <= a.area * 1e-6
    except ShapelyError:
        return False


def find_reusable_geometry(user, geometry):
    """Análise recente da mesma área desenhada (KML, coordenadas, shapefile)."""
    since = _reuse_since()
    if since is None:
        return None
    area = calculate_area_ha(geometry.wkt)
    candidates = (
        SearchHistory.objects
        .filter(user=user, search_type__in=GEOMETRY_SEARCH_TYPES, sucesso=True, created_at__gt=since,
                area_ha__gte=area * (1 - REUSE_AREA_TOLERANCE), area_ha__lte=area * (1 + REUSE_AREA_TOLERANCE))
        .only('pk', 'result_data')[:MAX_REUSE_CANDIDATES]
    )
    target = shapely_wkt.loads(geometry.wkt)
    for candidate in candidates:
        received = (candidate.result_data or {}).get('coordenadas_recebidas')
        try:
            other = shapely_wkt.loads(GEOSGeometry(received).wkt) if received else None
        except (GEOSException, ValueError, TypeError, ShapelyError):
            other = None
        if other is not None and _same_area(target, other):
            return _reused_summary(user, candidate)
    return None


# ---------------------------------------------------------------------------
# Análises
# ---------------------------------------------------------------------------

def analyze_car(user, car_number, aviso=None, search_type=SearchHistory.SearchType.CAR, forcar_nova=False,
                progress=None, extra=None):
    """`extra`: dados que vão junto no histórico (o recibo/demonstrativo lido do PDF)."""
    try:
        car = validate_car_number(car_number or '')
    except ValidationError as exc:
        raise QueryError(' '.join(exc.messages)) from None
    if not forcar_nova and not extra:
        reused = find_reusable(user, SearchHistory.SearchType.CAR, car, aviso)
        if reused:
            return reused
    resultado = _run(user, SearchForCar().execute, car, save_debug_files=False, user=user, progress=progress)
    if not resultado:
        raise QueryError(f'O CAR {car} não está na base do SICAR da plataforma (só há imóveis do Tocantins).')
    municipio, uf = _locate(user, resultado.get('alvo_wkt'))
    data = {'resultado': resultado, 'car_input': car, 'municipio': municipio, 'uf': uf, 'sucesso': True, **(extra or {})}
    if aviso:
        data['aviso'] = aviso
    return _finish(user, data, search_type)


def _analyze_geometry(user, geometry, label, search_type, forcar_nova=False, progress=None):
    if not forcar_nova:
        reused = find_reusable_geometry(user, geometry)
        if reused:
            return reused
    resultado = _run(user, SearchAll(user=user, progress=progress).execute, geometry, save_debug_files=False)
    municipio, uf = _locate(user, geometry.wkt)
    data = {
        'resultado': resultado,
        'coordenadas_recebidas': str(geometry),
        'car_input': (label or '').strip(),
        'municipio': municipio,
        'uf': uf,
        'sucesso': True,
    }
    return _finish(user, data, search_type)


def _point_municipality(user, lon, lat):
    if 'MunicipalBoundaries' in denied_layers(user):
        return None
    point = SimpleNamespace(index=0, lon=lon, lat=lat, municipality=None)
    locate_municipalities([point])
    return point.municipality


def _analyze_point(user, lon, lat, forcar_nova=False, progress=None):
    """Um ponto só: analisa o imóvel do SICAR onde ele cai, como a tela faz."""
    require_layer('SicarRecord', user)
    cars = cars_at_point(lon, lat)
    if not cars:
        municipio = _point_municipality(user, lon, lat)
        onde = f'fica em {municipio}/TO' if municipio else 'fica fora do Tocantins'
        return {
            'ponto': {'latitude': round(lat, 6), 'longitude': round(lon, 6)},
            'municipio': municipio,
            'imovel_encontrado': False,
            'mensagem': (f'O ponto {onde} e não cai em nenhum imóvel do SICAR. Para analisar uma área, '
                         'informe ao menos 3 vértices do perímetro ou a geometria (KML, GeoJSON ou WKT).'),
        }
    aviso = None
    if len(cars) > 1:
        aviso = (f'O ponto cai em {len(cars)} imóveis do SICAR (declarações sobrepostas); '
                 f'foi analisado o maior. Os outros: {", ".join(cars[1:])}.')
    return analyze_car(user, cars[0], aviso=aviso, search_type=SearchHistory.SearchType.COORDENADAS,
                       forcar_nova=forcar_nova, progress=progress)


def analyze_coordinates(user, coordinates, label=None, forcar_nova=False, progress=None):
    try:
        vertices = parse_vertices(coordinates)
        if len(vertices) == 1:
            return _analyze_point(user, *vertices[0], forcar_nova=forcar_nova, progress=progress)
        geometry = build_polygon(vertices)
    except CoordinatesInputError as exc:
        raise QueryError(str(exc)) from None
    _check_area(geometry.wkt)
    return _analyze_geometry(user, geometry, label, SearchHistory.SearchType.COORDENADAS, forcar_nova, progress)


def _geojson_geometries(obj):
    kind = obj.get('type') if isinstance(obj, dict) else None
    if kind == 'FeatureCollection':
        return [g for feature in obj.get('features') or [] for g in _geojson_geometries(feature)]
    if kind == 'Feature':
        return _geojson_geometries(obj.get('geometry'))
    if kind == 'GeometryCollection':
        return [g for geometry in obj.get('geometries') or [] for g in _geojson_geometries(geometry)]
    if kind:
        return [obj]
    return []


def _check_area(wkt):
    area = calculate_area_ha(wkt)
    if area > MAX_AREA_HA:
        raise QueryError(
            f'A área tem {area:,.0f} ha; o limite por análise é {MAX_AREA_HA:,} ha. '
            'Divida a área ou use o cruzamento em lote da plataforma.'.replace(',', '.'))


def parse_geometry(text):
    """Polígono (SIRGAS 2000) a partir de KML, GeoJSON ou WKT colado na conversa.

    Devolve (geometria, tipo de busca): KML conta como upload de KML; os
    demais, como coordenadas.
    """
    text = (text or '').strip().lstrip('﻿')
    if not text:
        raise QueryError('Informe a geometria: conteúdo de um KML, GeoJSON ou WKT.')
    if len(text) > MAX_GEOMETRY_CHARS:
        raise QueryError('Geometria grande demais para enviar pela conversa. Use o upload da plataforma.')

    if text.startswith('<'):
        try:
            gdf = KmlUploadService().extract_geodataframe(ContentFile(text.encode('utf-8'), name='area.kml'))
        except KmlUploadError as exc:
            raise QueryError(str(exc)) from None
        geometry = extract_geometry(gdf)
        if geometry is None:
            raise QueryError('O KML não tem nenhum polígono: é preciso o perímetro da área (não só pontos ou linhas).')
        _check_area(geometry.wkt)
        return geometry, SearchHistory.SearchType.KML

    try:
        if text.startswith('{'):
            parts = [shape(g) for g in _geojson_geometries(json.loads(text))]
            geom = unary_union(parts) if parts else None
        else:
            geom = shapely_wkt.loads(text)
    except (ValueError, TypeError, KeyError, AttributeError, ShapelyError):
        raise QueryError('Não consegui ler a geometria. Envie o conteúdo de um KML, um GeoJSON ou um WKT.') from None

    polygons = [g for g in getattr(geom, 'geoms', [geom]) if g is not None and g.geom_type in ('Polygon', 'MultiPolygon')]
    if not polygons:
        raise QueryError('A geometria precisa ser um polígono (o perímetro da área), não pontos ou linhas.')
    geom = shapely.force_2d(unary_union(polygons))
    if not geom.is_valid:
        geom = geom.buffer(0)
    minx, miny, maxx, maxy = geom.bounds
    if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
        raise QueryError('As coordenadas precisam estar em graus (latitude/longitude, SIRGAS 2000 ou WGS 84). '
                         'Coordenadas UTM não são aceitas aqui.')
    _check_area(geom.wkt)
    return GEOSGeometry(geom.wkt, srid=4674), SearchHistory.SearchType.COORDENADAS


def analyze_geometry(user, geometry_text, label=None, forcar_nova=False, progress=None):
    geometry, search_type = parse_geometry(geometry_text)
    return _analyze_geometry(user, geometry, label, search_type, forcar_nova, progress)


def analyze_sigef(user, parcel_code, forcar_nova=False, progress=None):
    code = (parcel_code or '').strip()
    if not code:
        raise QueryError('Informe o código da parcela do SIGEF.')
    require_layer('Sigef', user)
    if not forcar_nova:
        reused = find_reusable(user, SearchHistory.SearchType.SIGEF, code)
        if reused:
            return reused
    resultado = _run(user, SearchForSigef().execute, code, save_debug_files=False, user=user, progress=progress)
    if not resultado:
        raise QueryError(f'Parcela {code} não encontrada no SIGEF da plataforma.')
    municipio, uf = _locate(user, resultado.get('alvo_wkt'))
    data = {
        'resultado': resultado, 'car_input': code, 'source_model': 'Sigef',
        'municipio': municipio, 'uf': uf, 'sucesso': True,
    }
    return _finish(user, data, SearchHistory.SearchType.SIGEF)


def analyze_area_file(user, file_obj, label=None):
    """Área num arquivo enviado pelo link de envio: shapefile (ZIP), KML/KMZ ou GeoJSON."""
    name = (file_obj.name or '').lower()
    if name.endswith(('.geojson', '.json')):
        try:
            text = file_obj.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            raise QueryError('O GeoJSON precisa estar em UTF-8.') from None
        geometry, search_type = parse_geometry(text)
        return _analyze_geometry(user, geometry, label, search_type, forcar_nova=True)
    if name.endswith('.zip'):
        reader, search_type = ZipUploadService(), SearchHistory.SearchType.SHAPEFILE
    elif name.endswith(('.kml', '.kmz')):
        reader, search_type = KmlUploadService(), SearchHistory.SearchType.KML
    else:
        raise QueryError('Envie um shapefile compactado (.zip), um KML/KMZ ou um GeoJSON.')
    try:
        gdf = reader.extract_geodataframe(file_obj)
    except KmlUploadError as exc:
        raise QueryError(str(exc)) from None
    except Exception as exc:
        raise QueryError(f'Não consegui ler o arquivo: {exc}') from None
    geometry = extract_geometry(gdf)
    if geometry is None:
        raise QueryError('O arquivo não tem nenhum polígono: é preciso o perímetro da área (não só pontos ou linhas).')
    _check_area(geometry.wkt)
    return _analyze_geometry(user, geometry, label, search_type, forcar_nova=True)


def analyze_document(user, file_obj, kind, car_input=None):
    """PDF do Demonstrativo ou do Recibo do CAR: lê o documento e analisa o CAR dele, como a tela."""
    doc_type, search_type = DOCUMENTS[kind]
    if not (file_obj.name or '').lower().endswith('.pdf'):
        raise QueryError('Envie o PDF do documento.')
    try:
        context = DocumentDataContext(ExtractDocumentPdfPlumber(), DocumentsParserFactory.create_parser(doc_type))
        info = context.extract_data(file_obj)
    except Exception as exc:
        raise QueryError(f'Não consegui ler o PDF: {exc}') from None
    car = (info.car or car_input or '').strip()
    if not car:
        raise QueryError('Não achei o número do CAR no PDF. Informe o CAR junto com o envio.')
    return analyze_car(user, car, search_type=search_type, extra={kind: asdict(info)})


# ---------------------------------------------------------------------------
# Consultas sem análise
# ---------------------------------------------------------------------------

def locate_point(user, latitude, longitude):
    """Município, imóveis do SICAR e parcelas do SIGEF que contêm o ponto."""
    try:
        (lon, lat), = parse_vertices(f'{latitude}, {longitude}')
    except (CoordinatesInputError, ValueError):
        raise QueryError('Coordenada inválida: informe latitude e longitude em graus decimais.') from None
    denied = denied_layers(user)
    result = {'latitude': round(lat, 6), 'longitude': round(lon, 6)}
    if 'MunicipalBoundaries' not in denied:
        result['municipio'] = _point_municipality(user, lon, lat)
    if 'SicarRecord' not in denied:
        cars = cars_at_point(lon, lat)
        records = {
            r['car_number']: r for r in SicarRecord.objects.filter(car_number__in=cars)
            .values('car_number', 'status', 'area_ha', 'last_update')
        }
        result['imoveis_sicar'] = [
            {
                'car': car,
                'situacao': (records.get(car) or {}).get('status') or None,
                'area_ha': _num((records.get(car) or {}).get('area_ha')),
                'ultima_atualizacao': str((records.get(car) or {}).get('last_update') or '') or None,
            }
            for car in cars
        ]
    if 'Sigef' not in denied:
        point = SimpleNamespace(index=0, lon=lon, lat=lat, parcels=[])
        locate_sigef([point])
        result['parcelas_sigef'] = [
            {
                'codigo_parcela': p['code'], 'codigo_imovel': p['property_code'] or None,
                'nome': p['name'] or None, 'situacao': p['status'] or None, 'area_ha': _num(p['area_ha']),
            }
            for p in point.parcels
        ]
    return result


def list_analyses(user, search=None, kind=None, page=1):
    """Histórico do próprio usuário, como a tela "Meu histórico"."""
    denied = denied_layers(user)
    qs = SearchHistory.objects.filter(user=user)
    if 'Sigef' in denied:
        qs = qs.exclude(search_type=SearchHistory.SearchType.SIGEF)
    if 'SicarRecord' in denied:
        qs = qs.exclude(search_type__in=[
            SearchHistory.SearchType.CAR, SearchHistory.SearchType.DEMONSTRATIVO, SearchHistory.SearchType.RECIBO,
        ])
    if kind:
        valid = dict(SearchHistory.SearchType.choices)
        if kind not in valid:
            raise QueryError(f'Tipo inválido. Use um destes: {", ".join(valid)}.')
        qs = qs.filter(search_type=kind)
    if search and search.strip():
        qs = qs.filter(Q(car_input__icontains=search.strip()) | Q(municipio__icontains=search.strip()))
    if not denied:
        # `result_data` chega a vários MB: só as colunas da lista.
        qs = qs.defer('result_data')

    paginator = Paginator(qs, HISTORY_PAGE_SIZE)
    page_obj = paginator.get_page(page or 1)
    analyses = []
    for history in page_obj:
        overlaps = history.conflitos_count
        municipio = '' if 'MunicipalBoundaries' in denied else history.municipio
        if denied:
            data = dict(history.result_data or {})
            data['source_model'] = 'Sigef' if history.search_type == SearchHistory.SearchType.SIGEF else ''
            data['car_input'] = ''
            overlaps = (filter_result(data, denied=denied).get('resultado') or {}).get('total_areas_com_sobreposicao', 0)
        analyses.append({
            'analise_id': history.pk,
            'data': _local_time(history.created_at),
            'tipo': history.get_search_type_display(),
            'car_ou_identificacao': history.car_input or None,
            'municipio': municipio or None,
            'area_ha': _num(history.area_ha),
            'sobreposicoes': overlaps,
            'sucesso': history.sucesso,
            **({'erro': history.erro} if history.erro else {}),
        })
    return {
        'pagina': page_obj.number,
        'total_paginas': paginator.num_pages,
        'total_analises': paginator.count,
        'analises': analyses,
    }


def analysis_details(user, analise_id, base=None):
    """Resumo da análise ou, com `base`, todos os itens dessa base com os atributos."""
    historico, data = load_analysis(user, analise_id)
    if not base:
        if not data.get('sucesso'):
            _require_result(historico, data)
        return analysis_summary(historico, data)
    _require_result(historico, data)
    found = find_base(data.get('resultado'), base)
    nome = found.get('nome_base') or ''
    guia = base_guide(nome)
    areas = found.get('areas_encontradas') or []
    itens = []
    for item in areas[:MAX_DETAIL_ITEMS]:
        entry = {'descricao': item.get('item_info') or '', 'area_ha': _num(item.get('area'))}
        if _is_neutral(item):
            entry['fora_de_unidade'] = True
        entry['atributos'] = item_attributes(item)
        itens.append(entry)
    result = {
        'analise_id': historico.pk,
        'base': nome,
        'nivel': guia['nivel'],
        'o_que_e': guia['o_que_e'] or None,
        'o_que_significa_se_encontrado': guia['se_encontrado'] or None,
        'quantidade': len(areas),
        'area_total_ha': round(sum(_num(i.get('area')) or 0 for i in areas), 4),
        'itens': itens,
    }
    if len(areas) > MAX_DETAIL_ITEMS:
        result['itens_nao_listados'] = len(areas) - MAX_DETAIL_ITEMS
    return result


def bases_update_info(bases, analysis_date):
    """(quando cada base da análise foi atualizada, bases atualizadas depois da análise)."""
    dates = layer_update_dates()
    configs = {b['nome_base']: b for b in BASES_CONFIG}
    rows, newer = [], []
    for nome in bases:
        cfg = configs.get(nome)
        if cfg is None:
            continue
        when, origin = dates.get(cfg['modelo'], (None, None))
        row = {
            'base': nome,
            'atualizada_em': _local_time(when) if when else None,
            'fonte': cfg.get('fonte_api') or 'Arquivo enviado no painel da plataforma',
        }
        if when is None:
            row['observacao'] = 'Data de atualização não registrada.'
        elif origin == 'arquivo':
            row['observacao'] = 'Data do envio do arquivo no painel.'
        if when and when > analysis_date:
            newer.append(nome)
        rows.append(row)
    return rows, newer


def _location(ctx):
    loc = ctx.get('localizacao') or {}
    try:
        lat, lon = (float(loc[k].replace(',', '.')) for k in ('lat', 'lon'))
    except (KeyError, AttributeError, ValueError):
        return None
    return {'latitude': lat, 'longitude': lon, 'google_maps': loc.get('maps_url')}


def analysis_report(user, analise_id):
    """O mesmo conteúdo do relatório impresso: semáforo, bases com ocorrência,
    Reserva Legal, vegetação e comparativo de uso do solo (MapBiomas), mais a
    localização e a data de atualização de cada base."""
    from .exports import file_url

    historico, data = load_analysis(user, analise_id)
    _require_result(historico, data)
    ctx = build_report_context(deepcopy(data))
    tamanho = _num((ctx.get('resultado') or {}).get('tamanho_area'))
    atualizacoes, newer = bases_update_info(
        [b.get('nome_base') for b in data['resultado']['resultados_por_base']], historico.created_at)

    bases = [
        {
            'base': b.get('nome_base'),
            'titulo': b['guia']['titulo'],
            'nivel': b['guia']['nivel'],
            'o_que_e': b['guia']['o_que_e'] or None,
            'o_que_significa': b['guia']['se_encontrado'] or None,
            'area_ha': _num(b['total_area']),
            'percentual_do_imovel': _num(b['pct'], 2),
            'itens': [
                {'descricao': i.get('item_info') or '', 'area_ha': _num(i.get('area'))}
                for i in b['areas_relevantes'][:MAX_SUMMARY_ITEMS]
            ],
        }
        for b in ctx['bases_com_ocorrencia']
    ]
    rl = ctx['reserva_legal']
    uso = ctx.get('uso_solo')
    if uso and not uso.get('erro'):
        uso_solo = {
            'ano_antes': uso['ano_antes'],
            'ano_depois': uso['ano_depois'],
            'vegetacao_nativa_antes_ha': _num(uso['nativa_antes'], 2),
            'vegetacao_nativa_depois_ha': _num(uso['nativa_depois'], 2),
            'vegetacao_retirada_ha': _num(uso['suprimida'], 2),
            'vegetacao_regenerada_ha': _num(uso['regenerada'], 2),
            'destino_da_vegetacao_retirada': [
                {'uso': d['nome'], 'area_ha': _num(d['area'], 2)} for d in uso.get('destino_suprimida') or []
            ],
            'uso_por_grupo': [
                {'grupo': g['nome'], 'antes_ha': _num(g['antes'], 2), 'depois_ha': _num(g['depois'], 2)}
                for g in uso.get('grupos') or []
            ],
        }
    else:
        uso_solo = {'erro': (uso or {}).get('erro') or 'Comparativo indisponível.'}

    report = {
        'analise_id': historico.pk,
        'data': _local_time(historico.created_at),
        'car': ctx.get('numero_car') or data.get('car_input') or None,
        'nome_imovel': ctx.get('nome_imovel') or None,
        'proprietarios': ctx.get('proprietarios') or [],
        'municipio': data.get('municipio') or None,
        'uf': data.get('uf') or None,
        'localizacao': _location(ctx),
        'area_imovel_ha': tamanho,
        'veredito': VEREDITOS[ctx['veredito']],
        'alertas': ctx['n_alertas'],
        'pontos_de_atencao': ctx['n_atencao'],
        'perguntas': ctx['checklist'],
        'bases_com_ocorrencia': bases,
        'bases_so_com_encoste_minimo': [b.get('nome_base') for b in ctx['bases_so_residuais']],
        'bases_sem_ocorrencia': [b.get('nome_base') for b in ctx['bases_sem_ocorrencia']],
        'limite_residual_ha': _num(ctx['limite_residual']),
        'reserva_legal': {
            'exigida_ha': _num(rl['exigida'], 2),
            'declarada': rl['declarada_txt'] or None,
            'deficit_ha': _num(rl['deficit'], 2) if rl['tem_deficit'] else 0,
            'avaliada': rl['avaliada'],
        },
        'vegetacao_natural': [{'tipo': b['nome'], 'area_ha': _num(b['area'], 2)} for b in ctx['biomas']],
        'municipios': ctx['municipios_encontrados'],
        'uso_do_solo_mapbiomas': uso_solo,
        'atualizacao_das_bases': atualizacoes,
        'links': {**analysis_links(historico.pk), 'relatorio_pdf': file_url(user, historico.pk, 'relatorio', 'pdf')},
    }
    if newer:
        report['aviso_bases_atualizadas'] = (
            f'Depois desta análise foram atualizadas: {", ".join(newer)}. Para o resultado com os dados novos, '
            'faça a análise de novo (forcar_nova=true).')
    return report
