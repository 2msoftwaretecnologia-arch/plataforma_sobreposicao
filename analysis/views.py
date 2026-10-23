# Standard library
import io
import json
import re
import os
import tempfile
import zipfile
from dataclasses import asdict

# Django
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

import geopandas as gpd
from shapely import wkt as shapely_wkt

from control_panel.access_service import denied_layers, require_layer, filter_result, filter_batch_item

# Local apps – analysis
from analysis.models import CrossBatch, CrossBatchItem, SearchHistory
from analysis.services.analyze_coordinates.search_all import SearchAll
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.analyze_coordinates.search_for_sigef import SearchForSigef
from analysis.services.view_services.report_service import build_report_context
from analysis.services.view_services.imagery_service import (
    OGC_PROVIDERS,
    ImageryError,
    google_tile,
    imagery_config,
    landsat_legacy_scenes,
    landsat_legacy_tile,
    provider_layers,
    provider_source_url,
    provider_tile,
    wayback_releases,
)
from analysis.services.view_services.raster_tiles import cbers_scenes, cbers_tile, mapbiomas_tile
from analysis.services.view_services.result_map_formatter import format_data_map
from analysis.services.view_services.bases_3d import (
    MAX_TILE_ZOOM,
    MUNICIPIOS_JSON,
    bases_summary,
    cities_summary,
    property_outline,
    render_tile,
)
from analysis.services.view_services.zip_upload_service import ZipUploadService
from analysis.services.view_services.analysis_progress import (
    AnalysisCancelled,
    AnalysisProgress,
    cancel_progress,
    read_progress,
)
from analysis.services.view_services import cross_batch_service
from analysis.services.view_services.kmz_points_service import (
    KmzPointsError,
    car_details,
    car_perimeters,
    locate_cars,
    locate_municipalities,
    locate_sigef,
    parse_location_points,
    sigef_perimeters,
    summarize_cars,
    summarize_parcels,
)
from analysis.validators import validate_car_number

# Local apps – car_system / kernel
from car_system.utils import get_sicar_record
from kernel.utils import extract_geometry, locate_city_state

# Local apps – doc_extractor
from doc_extractor.services.parsers.constants import TypeDocument
from doc_extractor.services.parsers.context.extract_data_context import DocumentDataContext
from doc_extractor.services.parsers.factory.documents_parser_factory import DocumentsParserFactory
from doc_extractor.services.parsers.implement.extract_text.extract_pdf_plumber import (
    ExtractDocumentPdfPlumber,
)

def _save_search_history(request, data, search_type):
    """Persiste um registro em `SearchHistory` para cada busca executada,
    para que o painel administrativo possa listar o que os usuários
    pesquisaram. Não deve nunca quebrar o fluxo de busca do usuário."""
    try:
        resultado = data.get('resultado') or {}
        historico = SearchHistory.objects.create(
            user=request.user if request.user.is_authenticated else None,
            search_type=search_type,
            car_input=data.get('car_input') or '',
            municipio=data.get('municipio') or '',
            uf=data.get('uf') or '',
            area_ha=resultado.get('tamanho_area'),
            conflitos_count=resultado.get('total_areas_com_sobreposicao') or 0,
            sucesso=bool(data.get('sucesso')),
            erro=data.get('erro') or '',
            result_data=data,
        )
        # Vai junto para a sessão: o relatório é aberto por este id, e não pela
        # "última análise", para não trocar de análise se houver duas abas abertas.
        data['historico_id'] = historico.pk
    except Exception:
        pass


def _historico_data(request, pk):
    """Resultado salvo de uma busca do próprio usuário, já filtrado pelas permissões atuais."""
    historico = get_object_or_404(SearchHistory, pk=pk, user=request.user)
    stored = dict(historico.result_data or {})
    if historico.search_type == SearchHistory.SearchType.SIGEF:
        stored['source_model'] = 'Sigef'
    return historico, filter_result(stored, request.user)


class HomePageView(View):
    template_name = 'analysis/home.html'

    def get(self, request):
        return render(request, self.template_name)

class ResultsPageView(View):
    template_name = 'analysis/results.html'

    def get(self, request):
        data = filter_result(request.session.get('last_analysis') or {}, request.user)
        data['imagery'] = imagery_config()
        data = format_data_map(data)
        return render(request, self.template_name, data)

    def post(self, request):
        coordenadas_input = extract_geometry()
        car_input = request.POST.get('car_input', '').strip()
        if not coordenadas_input or not str(coordenadas_input).strip():
            return self._render_error(request, 'Por favor, insira coordenadas válidas.', car_input)
        return self._process_coordinates(request, coordenadas_input, car_input)

    # =====================================================================
    # Métodos auxiliares (Clean Code)
    # =====================================================================

    def _process_coordinates(self, request, coordenadas_input, car_input):
        """Executa a pesquisa nas bases, persiste na sessão e redireciona para GET."""
        try:
            resultado = SearchAll(user=request.user).execute(coordenadas_input)

            municipio, uf = None, None
            try:
                require_layer('MunicipalBoundaries', request.user)
                municipio, uf = locate_city_state(coordenadas_input)
            except Exception:
                pass

            data = {
                'resultado': resultado,
                'coordenadas_recebidas': str(coordenadas_input),
                'car_input': car_input,
                'municipio': municipio,
                'uf': uf,
                'sucesso': True
            }
            _save_search_history(request, data, SearchHistory.SearchType.COORDENADAS)
            request.session['last_analysis'] = data
            return redirect('results')

        except Exception as e:
            data = {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': str(coordenadas_input),
                'car_input': car_input,
                'sucesso': False
            }
            _save_search_history(request, data, SearchHistory.SearchType.COORDENADAS)
            request.session['last_analysis'] = data
            return redirect('results')

    def _render_error(self, request, message, car_input=None):
        return render(request, self.template_name, {
            'erro': message,
            'car_input': car_input,
            'sucesso': False,
            'imagery': imagery_config()
        })

class HistoricoView(View):
    """Lista as buscas que o próprio usuário logado já realizou."""
    template_name = 'analysis/historico.html'

    def get(self, request):
        denied = denied_layers(request.user)
        historico_qs = SearchHistory.objects.filter(user=request.user)
        if 'Sigef' in denied:
            historico_qs = historico_qs.exclude(search_type=SearchHistory.SearchType.SIGEF)
        if 'SicarRecord' in denied:
            historico_qs = historico_qs.exclude(search_type__in=[SearchHistory.SearchType.CAR, SearchHistory.SearchType.DEMONSTRATIVO, SearchHistory.SearchType.RECIBO])
        total_buscas = historico_qs.count()

        filtro_tipo = request.GET.get('tipo', '').strip()
        if filtro_tipo:
            historico_qs = historico_qs.filter(search_type=filtro_tipo)

        busca_texto = request.GET.get('q', '').strip()
        if busca_texto:
            historico_qs = historico_qs.filter(
                Q(car_input__icontains=busca_texto) | Q(municipio__icontains=busca_texto)
            )

        paginator = Paginator(historico_qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        for history in page_obj:
            if 'MunicipalBoundaries' in denied:
                history.municipio = ''
            if denied:
                data = dict(history.result_data or {})
                data['source_model'] = 'Sigef' if history.search_type == SearchHistory.SearchType.SIGEF else ''
                # A lista não inclui os resultados de bases revogadas.
                data['car_input'] = ''
                history.conflitos_count = (filter_result(data, denied=denied).get('resultado') or {}).get('total_areas_com_sobreposicao', 0)

        context = {
            'page_obj': page_obj,
            'total_buscas': total_buscas,
            'search_types': SearchHistory.SearchType.choices,
            'filtro_tipo': filtro_tipo,
            'busca_texto': busca_texto,
        }
        return render(request, self.template_name, context)


class HistoricoDetalheView(View):
    """Reabre o resultado de uma busca do próprio usuário logado."""

    def get(self, request, pk):
        historico, data = _historico_data(request, pk)
        data['imagery'] = imagery_config()
        data = format_data_map(data)
        data['is_historico'] = True
        data['historico'] = historico
        data['historico_back_url'] = reverse('historico')
        data['historico_back_label'] = 'Voltar para Meu Histórico'
        data['historico_eyebrow'] = 'Histórico de busca'

        return render(request, 'analysis/results.html', data)


class ReportPrintView(View):
    template_name = 'analysis/report_print.html'

    def get(self, request):
        pk = request.GET.get('historico', '')
        if pk:
            if not pk.isdigit():
                raise Http404
            _, data = _historico_data(request, int(pk))
        else:
            # Links antigos (sem id) continuam abrindo a última análise da sessão.
            data = filter_result(request.session.get('last_analysis') or {}, request.user)
        data = build_report_context(data)
        return render(request, self.template_name, data)


class DownloadPropertyShapefileView(View):
    def get(self, request):
        data = filter_result(request.session.get('last_analysis') or {}, request.user)
        resultado = data.get('resultado') or {}
        alvo_wkt = resultado.get('alvo_wkt')

        if not alvo_wkt:
            return HttpResponse('Nenhuma geometria da propriedade foi encontrada para exportação.', status=400)

        try:
            geom = shapely_wkt.loads(alvo_wkt)
        except Exception:
            return HttpResponse('Geometria da propriedade inválida.', status=400)

        car_value = data.get('car_input') or ''
        status_car = ''

        demonstrativo = data.get('demonstrativo') or {}
        status_car = demonstrativo.get('registration_status') or ''

        if not status_car and car_value:
            require_layer('SicarRecord', request.user)
            qs = get_sicar_record(car_number__iexact=car_value)
            if qs.exists():
                status_car = getattr(qs.first(), 'status', '') or ''

        gdf = gpd.GeoDataFrame(
            [{'car': car_value, 'status_car': status_car}],
            geometry=[geom],
            crs='EPSG:4674',
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, 'propriedade.shp')
            gdf.to_file(shp_path, driver='ESRI Shapefile', index=False)

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(tmpdir):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        arcname = os.path.basename(filepath)
                        zf.write(filepath, arcname)

        buffer.seek(0)

        filename = 'propriedade.shp.zip'
        if car_value:
            filename = f'propriedade_{car_value}.zip'

        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class DownloadPropertyKmlView(View):
    def get(self, request):
        data = filter_result(request.session.get('last_analysis') or {}, request.user)
        resultado = data.get('resultado') or {}
        alvo_wkt = resultado.get('alvo_wkt')

        if not alvo_wkt:
            return HttpResponse('Nenhuma geometria da propriedade foi encontrada para exportação.', status=400)

        try:
            geom = shapely_wkt.loads(alvo_wkt)
        except Exception:
            return HttpResponse('Geometria da propriedade inválida.', status=400)

        car_value = data.get('car_input') or ''
        status_car = ''

        demonstrativo = data.get('demonstrativo') or {}
        status_car = demonstrativo.get('registration_status') or ''

        if not status_car and car_value:
            require_layer('SicarRecord', request.user)
            qs = get_sicar_record(car_number__iexact=car_value)
            if qs.exists():
                status_car = getattr(qs.first(), 'status', '') or ''

        gdf = gpd.GeoDataFrame(
            [{'car': car_value, 'status_car': status_car}],
            geometry=[geom],
            crs='EPSG:4674',
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            kml_path = os.path.join(tmpdir, 'propriedade.kml')
            gdf.to_file(kml_path, driver='KML')

            with open(kml_path, 'rb') as f:
                content = f.read()

        filename = 'propriedade.kml'
        if car_value:
            filename = f'propriedade_{car_value}.kml'

        response = HttpResponse(content, content_type='application/vnd.google-earth.kml+xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

def _bases_3d_config(request):
    """Configuração do mapa 3D (camadas, tiles e cidades do tour)."""
    # MapLibre exige URL absoluta; os placeholders {z}/{x}/{y} e {base}
    # não passam pelo `reverse`, então trocamos um tile fictício por eles.
    sample = request.build_absolute_uri(reverse('base_tiles', args=('BASE', 0, 0, 0)))
    return {
        'tilesUrl': sample.replace('/BASE/0/0/0.pbf', '/{base}/{z}/{x}/{y}.pbf'),
        'maxTileZoom': MAX_TILE_ZOOM,
        'bases': [b for b in bases_summary() if b['modelo'] not in denied_layers(request.user)],
        'cities': cities_summary() if 'SicarRecord' not in denied_layers(request.user) else [],
        'propertyUrl': reverse('base_property_outline'),
        # `{job}` é trocado pelo id da análise gerado no navegador.
        'progressUrl': reverse('analysis_progress', args=('JOB',)).replace('JOB', '{job}'),
        'cancelUrl': reverse('analysis_cancel', args=('JOB',)).replace('JOB', '{job}'),
    }


def _recent_searches(user, limit=5):
    """Últimos CARs analisados pelo usuário (sem repetir), para o atalho
    "Buscas recentes" no painel da página inicial."""
    denied = denied_layers(user)
    if 'SicarRecord' in denied:
        return []
    qs = (
        SearchHistory.objects
        .filter(user=user, sucesso=True, search_type__in=[
            SearchHistory.SearchType.CAR,
            SearchHistory.SearchType.DEMONSTRATIVO,
            SearchHistory.SearchType.RECIBO,
        ])
        .exclude(car_input='')
        # `result_data` chega a vários MB: só as colunas da lista.
        .only('pk', 'car_input', 'municipio', 'area_ha', 'created_at')[:40]
    )
    recent, seen = [], set()
    for history in qs:
        car = history.car_input.strip().upper()
        if car in seen:
            continue
        seen.add(car)
        if 'MunicipalBoundaries' in denied:
            history.municipio = ''
        recent.append(history)
        if len(recent) == limit:
            break
    return recent


class AnalysisProgressView(View):
    """Andamento da análise em curso (ver `analysis_progress`)."""

    def get(self, request, job_id):
        return JsonResponse(read_progress(request.user, job_id) or {})


class AnalysisCancelView(View):
    """Botão "Cancelar análise" da tela do mapa 3D."""

    def post(self, request, job_id):
        cancel_progress(request.user, job_id)
        return HttpResponse(status=204)


class UploadZipCarView(View):
    """Página inicial depois do login: mapa 3D do SICAR com o tour de cidade
    em cidade e o formulário de análise no canto."""
    template_upload = 'analysis/bases_3d.html'
    template_index = 'analysis/results.html'
    # Trocado em `post` pelo andamento da análise pedida; este é no-op.
    progress = AnalysisProgress()

    def get(self, request):
        return self._render_form(request, {})

    def _render_form(self, request, context):
        config = _bases_3d_config(request)
        # Voltou com erro: o mapa fica no imóvel buscado em vez de recomeçar o tour.
        config['searchError'] = bool(context.get('erro'))
        context['bases_3d_config'] = config
        context['recent_searches'] = _recent_searches(request.user)
        return render(request, self.template_upload, context)

    def post(self, request):
        # Andamento para a tela (ver `analysis_progress`): a página consulta
        # `AnalysisProgressView` enquanto espera esta resposta.
        self.progress = AnalysisProgress.from_request(request)
        try:
            response = self._post(request)
        except AnalysisCancelled:
            # A página já desistiu da resposta; 204 não troca de página.
            return HttpResponse(status=204)
        if response.status_code == 302:
            self.progress.finish()
        return response

    def _post(self, request):
        zip_file = request.FILES.get('zip_file')
        car_input = request.POST.get('car_input', '').strip()
        mode = request.POST.get('mode', '').strip()

        context = {'car_input': car_input}

        if mode == 'demostrativo':
            return self._handle_document_upload(
                request,
                request.FILES.get('demo_file'),
                TypeDocument.STATEMENT,
                'demonstrativo',
                car_input,
                'Por favor, envie um arquivo PDF do demonstrativo.',
                'Erro ao processar o demonstrativo',
                context
            )

        elif mode == 'recibo':
            return self._handle_document_upload(
                request,
                request.FILES.get('recibo_file'),
                TypeDocument.RECEIPT,
                'recibo',
                car_input,
                'Por favor, envie um arquivo PDF do recibo.',
                'Erro ao processar o recibo',
                context
            )

        # --------------------------------------
        # 1) Busca pelo número do CAR (sem ZIP): o número é obrigatório e
        #    precisa seguir o formato oficial do CAR (ver `analysis/validators.py`).
        # --------------------------------------
        if mode == 'car' or (not zip_file and car_input):
            try:
                car_input = validate_car_number(car_input)
            except ValidationError as e:
                context['erro'] = e.message
                context['car_input'] = car_input
                return self._render_form(request, context)

            context['car_input'] = car_input
            return self._handle_only_car(request, car_input, context)

        # --------------------------------------
        # 2) Nenhum arquivo enviado
        # --------------------------------------
        if not zip_file:
            context['erro'] = 'Por favor, envie um arquivo ZIP ou informe o número do CAR.'
            return self._render_form(request, context)

        # --------------------------------------
        # 3) Caso ZIP enviado
        # --------------------------------------
        try:
            self.progress.stage('Lendo o shapefile')
            zip_dataframe = ZipUploadService().extract_geodataframe(zip_file)

            if zip_dataframe is None or zip_dataframe.empty:
                context['erro'] = 'O arquivo ZIP não contém dados geográficos válidos.'
                return self._render_form(request, context)

            coordenadas_input = extract_geometry(zip_dataframe)

            if not coordenadas_input or not str(coordenadas_input).strip():
                context['erro'] = 'Não foi possível extrair coordenadas do shapefile enviado.'
                return self._render_form(request, context)

            return self._process_coordinates(request, coordenadas_input, car_input)

        except zipfile.BadZipFile:
            context['erro'] = 'Arquivo ZIP inválido ou corrompido.'
            return self._render_form(request, context)

        except AnalysisCancelled:
            raise

        except Exception as e:
            context['erro'] = f'Erro ao processar o arquivo: {str(e)}'
            return self._render_form(request, context)

    # =====================================================================
    # Métodos auxiliares
    # =====================================================================

    def _get_car_data(self, car_number, user=None):
        """Busca dados do CAR e localidade."""
        resultado = {}
        municipio, state = None, None
        
        if car_number:
            try:
                self.progress.stage('Localizando o imóvel', car=car_number)
                resultado = SearchForCar().execute(car_number, user=user, progress=self.progress) or {}
                qs = get_sicar_record(car_number__iexact=car_number)
                if qs.exists():
                    geometry = qs.first().geometry
                    require_layer('MunicipalBoundaries', user)
                    self.progress.stage('Identificando o município')
                    municipio, state = locate_city_state(geometry)
            except AnalysisCancelled:
                raise
            except Exception:
                pass
        return resultado, municipio, state

    _DOC_SEARCH_TYPE = {
        'demonstrativo': SearchHistory.SearchType.DEMONSTRATIVO,
        'recibo': SearchHistory.SearchType.RECIBO,
    }

    def _handle_document_upload(self, request, file_obj, doc_type, result_key, car_input, missing_msg, error_prefix, context):
        """Processa upload de documentos (Recibo ou Demonstrativo)."""
        if not file_obj:
            context['erro'] = missing_msg
            return self._render_form(request, context)

        try:
            self.progress.stage('Lendo o documento')
            parser = DocumentsParserFactory.create_parser(doc_type)
            extractor = ExtractDocumentPdfPlumber()
            ctx = DocumentDataContext(extractor, parser)
            info = ctx.extract_data(file_obj)
            
            car_extraido = (info.car or car_input or '').strip()

            resultado, municipio, state = self._get_car_data(car_extraido, request.user)

            #esultado, municipio, state = {}, "Palmas", "TO"
            data = {
                'resultado': resultado,
                result_key: asdict(info),
                'car_input': car_extraido,
                'municipio': municipio,
                'uf': state,
                'sucesso': True
            }

            _save_search_history(
                request, data, self._DOC_SEARCH_TYPE.get(result_key, SearchHistory.SearchType.DEMONSTRATIVO)
            )
            request.session['last_analysis'] = data
            return redirect('results')

        except AnalysisCancelled:
            raise
        except Exception as e:
            context['erro'] = f'{error_prefix}: {str(e)}'
            return self._render_form(request, context)

    def _handle_only_car(self, request, car_input, context):
        """Processa requisição apenas com o CAR (sem ZIP)."""
        try:
            resultado, municipality, state = self._get_car_data(car_input, request.user)

            data = {
                'resultado': resultado,
                'car_input': car_input,
                'municipio': municipality,
                'uf': state,
                'sucesso': True
            }
            _save_search_history(request, data, SearchHistory.SearchType.CAR)
            request.session['last_analysis'] = data
            return redirect('results')

        except AnalysisCancelled:
            raise
        except Exception as e:
            context['erro'] = f'Erro ao analisar pelo CAR: {str(e)}'
            return self._render_form(request, context)

    def _process_coordinates(self, request, coordenadas_input, car_input):
        """Processa os dados extraídos do shapefile."""
        try:
            resultado = SearchAll(user=request.user, progress=self.progress).execute(coordenadas_input)
            municipio, uf = None, None
            try:
                require_layer('MunicipalBoundaries', request.user)
                self.progress.stage('Identificando o município')
                municipio, uf = locate_city_state(coordenadas_input)
            except Exception:
                pass
            data = {
                'resultado': resultado,
                'coordenadas_recebidas': str(coordenadas_input),
                'car_input': car_input,
                'municipio': municipio,
                'uf': uf,
                'sucesso': True
            }
            _save_search_history(request, data, SearchHistory.SearchType.SHAPEFILE)
            request.session['last_analysis'] = data
            return redirect('results')
        except AnalysisCancelled:
            raise
        except Exception as e:
            data = {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': str(coordenadas_input),
                'car_input': car_input,
                'sucesso': False
            }
            _save_search_history(request, data, SearchHistory.SearchType.SHAPEFILE)
            request.session['last_analysis'] = data
            return redirect('results')

def _municipios_por_codigo() -> dict:
    """Nome dos municípios do Tocantins pelo código IBGE."""
    try:
        return {m['codigo']: m['nome'] for m in json.loads(MUNICIPIOS_JSON.read_text(encoding='utf-8'))}
    except (OSError, ValueError):
        return {}


def _data_br(value) -> str:
    return value.strftime('%d/%m/%Y') if value else ''


class LocalizacoesKmzView(View):
    """Recebe um ou mais KMZ/KML de localizações (um Placemark por ponto) e
    mostra em qual imóvel do SICAR cai o ponto central de cada uma. O
    cruzamento do CAR inteiro com as demais bases é feito sob demanda, pelo
    fluxo de busca por CAR que já existe (`UploadZipCarView`, modo `car`)."""
    template_name = 'analysis/localizacoes.html'

    def get(self, request):
        return render(request, self.template_name, {})

    def post(self, request):
        files = request.FILES.getlist('kmz_files')
        if not files:
            return render(request, self.template_name, {'erro': 'Envie ao menos um arquivo KMZ ou KML.'})
        invalid = [f.name for f in files if not f.name.lower().endswith(('.kmz', '.kml'))]
        if invalid:
            return render(request, self.template_name, {
                'erro': f'Só são aceitos arquivos .kmz ou .kml: {", ".join(invalid)}.'
            })

        points, skipped = [], []
        try:
            for f in files:
                file_points, file_skipped = parse_location_points(f, first_index=len(points) + 1, source=f.name)
                points += file_points
                skipped += [f'{name} ({f.name})' for name in file_skipped]
            denied = denied_layers(request.user)
            if 'SicarRecord' not in denied:
                locate_cars(points)
            if 'Sigef' not in denied:
                locate_sigef(points)
        except KmzPointsError as e:
            return render(request, self.template_name, {'erro': str(e)})
        except Exception as e:
            return render(request, self.template_name, {'erro': f'Erro ao processar os arquivos: {e}'})

        try:
            require_layer('MunicipalBoundaries', request.user)
            locate_municipalities(points)
            municipios_ok = True
        except Exception:
            # Sem os limites municipais a tela só não separa quem está fora do TO.
            municipios_ok = False

        cars = summarize_cars(points)
        car_numbers = [c['car_number'] for c in cars]
        try:
            perimeters = car_perimeters(car_numbers)
        except Exception:
            # Sem o perímetro a tela continua útil (pontos e tabelas).
            perimeters = {}
        try:
            details = car_details(car_numbers)
            if 'DeclaredHydrography' in denied_layers(request.user):
                for detail in details.values():
                    detail['hydrography'] = []
        except Exception:
            details = {}
        municipios = _municipios_por_codigo() if 'MunicipalBoundaries' not in denied_layers(request.user) else {}

        parcels = summarize_parcels(points)
        try:
            parcel_perimeters = sigef_perimeters([p['code'] for p in parcels])
        except Exception:
            parcel_perimeters = {}
        parcel_position = {p['code']: i for i, p in enumerate(parcels)}
        with_parcel = sum(1 for p in points if p.parcels)

        sources = [f.name for f in files]
        car_position = {c['car_number']: i for i, c in enumerate(cars)}
        with_car = sum(1 for p in points if p.cars)
        outside_to = sum(1 for p in points if p.municipality is None) if municipios_ok else None
        context = {
            'arquivos': sources,
            'points': points,
            'cars': cars,
            'skipped': skipped,
            'total_points': len(points),
            'distinct_positions': len({(round(p.lon, 5), round(p.lat, 5)) for p in points}),
            'with_car': with_car,
            'without_car': len(points) - with_car,
            'outside_to': outside_to,
            'without_car_in_to': len(points) - with_car - (outside_to or 0),
            'from_plus_code': sum(1 for p in points if p.from_plus_code),
            'divergent': sum(1 for p in points if p.is_divergent),
            'lote_minutos': cross_batch_service.estimate_minutes(len(cars)),
            'parcels': parcels,
            'with_parcel': with_parcel,
            'without_parcel_in_to': len(points) - with_parcel - (outside_to or 0),
            'lote_minutos_sigef': cross_batch_service.estimate_minutes(len(parcels)),
            # Dados compactos para o mapa e para as tabelas, que são montadas no
            # navegador (com vários arquivos são milhares de localizações).
            'map_points': [
                {
                    'i': p.index,
                    'n': p.name,
                    'f': sources.index(p.source),
                    'lat': round(p.lat, 6),
                    'lon': round(p.lon, 6),
                    'plus': p.from_plus_code,
                    'div': round(p.divergence_m) if p.is_divergent else None,
                    'mun': p.municipality or '',
                    'fora': municipios_ok and p.municipality is None,
                    # Posições dos CARs em `map_cars` e das parcelas em `map_parcels`.
                    'cars': [car_position[c['car_number']] for c in p.cars],
                    'parc': [parcel_position[c['code']] for c in p.parcels],
                }
                for p in points
            ],
            'map_sources': sources,
            'map_parcels': [
                {
                    'code': c['code'],
                    'imovel': c['property_code'],
                    'nome': c['name'],
                    'status': c['status'],
                    'area_ha': round(c['area_ha'], 2) if c['area_ha'] is not None else None,
                    'mun': c['municipality'],
                    'pontos': [p.index for p in c['points']],
                    'geom': parcel_perimeters.get(c['code']),
                }
                for c in parcels
            ],
            'map_cars': [
                {
                    'car': c['car_number'],
                    'status': c['status'],
                    'area_ha': round(c['area_ha'], 2) if c['area_ha'] is not None else None,
                    'pontos': [p.index for p in c['points']],
                    'geom': perimeters.get(c['car_number']),
                    # O código IBGE do município está no número do CAR (UF-<7 dígitos>-<hash>).
                    'mun': municipios.get(c['car_number'][3:10], ''),
                    'upd': _data_br(details.get(c['car_number'], {}).get('last_update')),
                    'hidro': [
                        {
                            'tema': h['theme'],
                            'n': h['count'],
                            'ha': round(h['area_ha'], 2) if h['area_ha'] is not None else None,
                        }
                        for h in details.get(c['car_number'], {}).get('hydrography', [])
                    ],
                }
                for c in cars
            ],
        }
        return render(request, self.template_name, context)


class AnaliseParcelaSigefView(View):
    """Cruza uma parcela do SIGEF inteira com as bases e abre a mesma página
    de resultados da busca por CAR (botão "Cruzar com as bases" da ficha da
    parcela na tela de Localizações e do relatório do lote)."""

    def post(self, request):
        code = request.POST.get('parcela', '').strip()
        data = {'car_input': code, 'source_model': 'Sigef', 'sucesso': True}
        try:
            resultado = SearchForSigef().execute(code, user=request.user)
            if not resultado:
                raise ValueError('Parcela não encontrada no SIGEF.')
            data.update({'resultado': resultado, 'municipio': _municipio_da_parcela(code) if 'MunicipalBoundaries' not in denied_layers(request.user) else '', 'uf': 'TO'})
        except Exception as e:
            data.update({'sucesso': False, 'erro': f'Erro ao analisar a parcela do SIGEF: {e}'})
        _save_search_history(request, data, SearchHistory.SearchType.SIGEF)
        request.session['last_analysis'] = data
        return redirect('results')


def _municipio_da_parcela(code: str) -> str:
    """Município do Tocantins onde fica (o interior de) uma parcela do SIGEF."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT m."NOME" FROM tb_area_sigef s
            JOIN tb_area_municipios m ON ST_Intersects(m.geometria_util, ST_PointOnSurface(s.geometria_util))
            WHERE s.codigo_imo = %s LIMIT 1
        """, [code])
        row = cursor.fetchone()
    return row[0] if row else ''


# =====================================================================
# Cruzamento em lote dos CARs encontrados em Localizações
# =====================================================================

def _get_batch_for(request, pk):
    """O lote, se for do usuário logado (equipe vê todos)."""
    qs = CrossBatch.objects.all() if request.user.is_staff else CrossBatch.objects.filter(user=request.user)
    batch = get_object_or_404(qs, pk=pk)
    require_layer('Sigef' if batch.kind == CrossBatch.Kind.SIGEF else 'SicarRecord', request.user)
    return batch


def _batch_item_row(item) -> dict:
    """Linha compacta de um CAR do lote para o relatório (JSON no navegador)."""
    return {
        'id': item.pk,
        'car': item.car_number,
        'mun': item.municipio,
        'st': item.car_status,
        'area': round(item.area_ha, 2) if item.area_ha is not None else None,
        'pontos': item.points,
        'extra': item.extra,
        'status': item.status,
        'err': item.error,
        'crit': item.critical_count,
        'warn': item.warning_count,
        'ov': item.overlap_count,
        'fim': item.finished_at.isoformat() if item.finished_at else None,
        's': item.summary,
    }


# Como chamar os itens de cada tipo de lote nas telas.
_BATCH_LABELS = {
    CrossBatch.Kind.CAR: {
        'kind': 'car', 'base': 'SICAR', 'noun': 'CAR', 'noun_pl': 'CARs', 'o': 'o', 'os': 'os',
        'item_title': 'Imóvel do CAR',
    },
    CrossBatch.Kind.SIGEF: {
        'kind': 'sigef', 'base': 'SIGEF', 'noun': 'parcela', 'noun_pl': 'parcelas', 'o': 'a', 'os': 'as',
        'item_title': 'Parcela do SIGEF',
    },
}


def _batch_labels(batch) -> dict:
    return _BATCH_LABELS.get(batch.kind, _BATCH_LABELS[CrossBatch.Kind.CAR])


def _batch_progress(batch) -> dict:
    return {
        'status': batch.status,
        'status_label': batch.get_status_display(),
        'processed': batch.processed,
        'total': batch.total,
        'percent': batch.percent,
        'error': batch.error,
    }


class LoteCruzamentoCreateView(View):
    """Cria o lote com os CARs enviados pela tela de Localizações e dispara o
    processamento em segundo plano."""

    def post(self, request):
        try:
            cars = json.loads(request.POST.get('cars') or '[]')
        except ValueError:
            cars = []
        if not isinstance(cars, list) or not cars:
            return redirect('localizacoes_kmz')
        kind = CrossBatch.Kind.SIGEF if request.POST.get('base') == 'sigef' else CrossBatch.Kind.CAR
        batch = cross_batch_service.create_batch(request.user, request.POST.get('titulo', '').strip(), cars, kind)
        if not batch.total:
            batch.delete()
            return redirect('localizacoes_kmz')
        cross_batch_service.start_batch(batch)
        return redirect('lote_cruzamento', pk=batch.pk)


def _nome_arquivo_curto(nome: str) -> str:
    """'Trajetos_Florestal_Agosto_2022.xlsx (1).kmz' -> 'Trajetos Florestal Agosto 2022'."""
    nome = re.sub(r'\.(kmz|kml)$', '', nome.strip(), flags=re.I)
    nome = re.sub(r'\s*\(\d+\)$', '', nome)            # cópia baixada de novo: "(1)"
    nome = re.sub(r'\.(xlsx?|csv)$', '', nome, flags=re.I)  # planilha de origem
    nome = re.sub(r'\s*\(\d+\)$', '', nome)
    return re.sub(r'[_]+', ' ', nome).strip() or nome


class LotesCruzamentoListView(View):
    template_name = 'analysis/lotes_cruzamento.html'

    def get(self, request):
        denied = denied_layers(request.user)
        batches = CrossBatch.objects.filter(user=request.user)
        if 'SicarRecord' in denied:
            batches = batches.exclude(kind=CrossBatch.Kind.CAR)
        if 'Sigef' in denied:
            batches = batches.exclude(kind=CrossBatch.Kind.SIGEF)
        page_obj = Paginator(batches, 15).get_page(request.GET.get('page'))
        for lote in page_obj:
            if cross_batch_service.resume_if_stale(lote):
                lote.refresh_from_db()
            lote.labels = _batch_labels(lote)
            # O título é a lista de arquivos enviados ("a.kmz, b.kmz"); vira etiquetas na tela.
            lote.arquivos = [
                {'nome': _nome_arquivo_curto(a), 'completo': a.strip()}
                for a in (lote.title or '').split(', ') if a.strip()
            ]
        algum_processando = any(
            lote.status in (CrossBatch.Status.PENDING, CrossBatch.Status.RUNNING) for lote in page_obj
        )
        return render(request, self.template_name, {'page_obj': page_obj, 'algum_processando': algum_processando})


class LoteCruzamentoDetailView(View):
    template_name = 'analysis/lote_cruzamento.html'

    def get(self, request, pk):
        batch = _get_batch_for(request, pk)
        cross_batch_service.resume_if_stale(batch)
        batch.refresh_from_db()
        denied = denied_layers(request.user)
        return render(request, self.template_name, {
            'batch': batch,
            'labels': _batch_labels(batch),
            'progress': _batch_progress(batch),
            'items': [_batch_item_row(filter_batch_item(item, denied=denied)) for item in batch.items.all()],
        })


class LoteCruzamentoStatusView(View):
    """Progresso do lote + CARs concluídos depois de `desde` (ISO), para a
    página do relatório ir se atualizando sem recarregar."""

    def get(self, request, pk):
        batch = _get_batch_for(request, pk)
        cross_batch_service.resume_if_stale(batch)
        batch.refresh_from_db()
        denied = denied_layers(request.user)
        items = batch.items.exclude(status=CrossBatchItem.Status.PENDING)
        desde = request.GET.get('desde')
        if desde:
            try:
                from django.utils.dateparse import parse_datetime
                desde_dt = parse_datetime(desde)
                if desde_dt:
                    items = items.filter(finished_at__gt=desde_dt)
            except ValueError:
                pass
        return JsonResponse({
            'progress': _batch_progress(batch),
            'items': [_batch_item_row(filter_batch_item(item, denied=denied)) for item in items],
        })


class LoteCruzamentoPrintView(View):
    """Relatório para imprimir/salvar em PDF: um CAR por página."""
    template_name = 'analysis/lote_cruzamento_print.html'

    def get(self, request, pk):
        batch = _get_batch_for(request, pk)
        denied = denied_layers(request.user)
        items = batch.items.filter(status=CrossBatchItem.Status.DONE)
        car = request.GET.get('car', '').strip()
        nivel = request.GET.get('nivel', '').strip()
        if car:
            items = items.filter(car_number__iexact=car)
        if not items.exists() and car:
            raise Http404('CAR não encontrado neste lote.')
        cars = [self._print_car(filter_batch_item(item, denied=denied)) for item in items.order_by('-critical_count', '-warning_count', 'car_number')]
        if nivel == 'critical':
            cars = [c for c in cars if c['item'].critical_count]
        elif nivel == 'alertas':
            cars = [c for c in cars if c['item'].critical_count or c['item'].warning_count]
        cars.sort(key=lambda c: (-c['item'].critical_count, -c['item'].warning_count, c['item'].car_number))
        return render(request, self.template_name, {
            'batch': batch,
            'labels': _batch_labels(batch),
            'cars': cars,
            'nivel': nivel,
            'um_car': bool(car),
            'totais': {
                'cars': len(cars),
                'criticos': sum(1 for c in cars if c['item'].critical_count),
                'atencao': sum(1 for c in cars if not c['item'].critical_count and c['item'].warning_count),
            },
        })

    _SEV_ORDER = {'critical': 0, 'warning': 1, 'info': 2}
    _SEV_LABEL = {'critical': 'Crítico', 'warning': 'Atenção', 'info': 'Informativa'}

    def _print_car(self, item) -> dict:
        summary = item.summary or {}
        area_car = summary.get('tamanho_area') or item.area_ha or 0
        bases = sorted(summary.get('bases') or [],
                       key=lambda b: (self._SEV_ORDER.get(b.get('severity'), 3), -(b.get('total_area') or 0)))
        com = []
        for b in bases:
            if not (b.get('count') or b.get('neutral_count')):
                continue
            sev = b['severity'] if b.get('count') else 'info'
            com.append({
                **b,
                'nome_curto': _base_name_short(b.get('nome', '')),
                'sev': sev,
                'sev_label': self._SEV_LABEL[sev] if b.get('count') else 'Sem restrição',
                'pct': round(b['total_area'] * 100 / area_car, 1) if b.get('count') and area_car else None,
            })
        return {
            'item': item,
            'area_car': area_car,
            'status_label': {
                'AT': 'Ativo', 'PE': 'Pendente', 'SU': 'Suspenso', 'CA': 'Cancelado',
                'CERTIFICADA': 'Certificada', 'REGISTRADA': 'Registrada',
            }.get((item.car_status or '').upper(), item.car_status or '—'),
            'bases': com,
            'sem': [_base_name_short(b.get('nome', '')) for b in bases if not (b.get('count') or b.get('neutral_count'))],
        }


def _base_name_short(nome: str) -> str:
    """'Base de Dados de Unidades de Conservação' -> 'Unidades de Conservação'."""
    return re.sub(r'^Base de( Dados)?( de)?\s*', '', nome or '', flags=re.I) or nome


def termos(request):
    return render(request, 'analysis/termos_de_uso.html')


class BaseTileView(View):
    """Vector tile (MVT) de uma base, recortado pelo Tocantins."""

    def get(self, request, modelo, z, x, y):
        require_layer(modelo, request.user)
        tile = render_tile(modelo, z, x, y)
        if not tile:
            return HttpResponse(status=204)
        response = HttpResponse(tile, content_type='application/vnd.mapbox-vector-tile')
        response['Cache-Control'] = 'private, max-age=3600'
        return response


class PropertyOutlineView(View):
    """Perímetro do imóvel buscado pelo CAR, para a animação de busca no
    mapa 3D enquanto a análise roda no servidor."""

    def get(self, request):
        require_layer('SicarRecord', request.user)
        outline = property_outline(request.GET.get('car', '').strip())
        if not outline:
            return JsonResponse({}, status=404)
        return JsonResponse(outline)


def _image_tile_response(fetch):
    """Resposta de um tile de imagem de satélite vindo por proxy: 204 sem
    imagem naquele ponto, 502 quando o provedor falha."""
    try:
        tile = fetch()
    except ImageryError:
        return HttpResponse(status=502)
    if tile is None:
        return HttpResponse(status=204)
    content, content_type = tile
    response = HttpResponse(content, content_type=content_type)
    response['Cache-Control'] = 'private, max-age=86400'
    return response


def _require_provider(provider):
    if provider not in OGC_PROVIDERS or not provider_source_url(provider):
        raise Http404


class ProviderLayersView(View):
    """Camadas/mosaicos de um provedor OGC (Planet, Copernicus) para o
    seletor do mapa."""

    def get(self, request, provider):
        _require_provider(provider)
        try:
            return JsonResponse({'layers': provider_layers(provider)})
        except ImageryError as e:
            return JsonResponse({'erro': str(e), 'layers': []}, status=502)


class ProviderTileView(View):
    def get(self, request, provider, layer, z, x, y):
        _require_provider(provider)
        return _image_tile_response(lambda: provider_tile(provider, layer, z, x, y))


class GoogleTileView(View):
    def get(self, request, z, x, y):
        return _image_tile_response(lambda: google_tile(z, x, y))


class MapbiomasTileView(View):
    """Uso do solo ou área queimada do MapBiomas, gerado a partir do GeoTIFF."""

    def get(self, request, product, year, z, x, y):
        return _image_tile_response(lambda: mapbiomas_tile(product, year, z, x, y))


class CbersScenesView(View):
    """Cenas CBERS-4A de 2 m que cobrem o ponto (?lat=&lon=)."""

    def get(self, request):
        try:
            lat = float(request.GET.get('lat', ''))
            lon = float(request.GET.get('lon', ''))
        except ValueError:
            return JsonResponse({'erro': 'Informe lat e lon.', 'scenes': []}, status=400)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return JsonResponse({'erro': 'Coordenadas inválidas.', 'scenes': []}, status=400)
        try:
            return JsonResponse({'scenes': cbers_scenes(lon, lat)})
        except ImageryError as e:
            return JsonResponse({'erro': str(e), 'scenes': []}, status=502)


class CbersTileView(View):
    def get(self, request, scene, z, x, y):
        return _image_tile_response(lambda: cbers_tile(scene, z, x, y))


class LandsatLegacyScenesView(View):
    """Cenas Landsat 4/5/7 (1984–2012) que cobrem o ponto (?lat=&lon=)."""

    def get(self, request):
        try:
            lat = float(request.GET.get('lat', ''))
            lon = float(request.GET.get('lon', ''))
        except ValueError:
            return JsonResponse({'erro': 'Informe lat e lon.', 'scenes': []}, status=400)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return JsonResponse({'erro': 'Coordenadas inválidas.', 'scenes': []}, status=400)
        try:
            return JsonResponse({'scenes': landsat_legacy_scenes(lon, lat)})
        except ImageryError as e:
            return JsonResponse({'erro': str(e), 'scenes': []}, status=502)


class LandsatLegacyTileView(View):
    def get(self, request, scene, comp, z, x, y):
        return _image_tile_response(lambda: landsat_legacy_tile(scene, comp, z, x, y))


class WaybackReleasesView(View):
    """Datas da imagem histórica da Esri (Wayback)."""

    def get(self, request):
        try:
            return JsonResponse({'releases': wayback_releases()})
        except ImageryError as e:
            return JsonResponse({'erro': str(e), 'releases': []}, status=502)
