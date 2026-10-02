# Standard library
import io
import json
import os
import tempfile
import zipfile
from dataclasses import asdict

# Django
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

import geopandas as gpd
from shapely import wkt as shapely_wkt

# Local apps – analysis
from analysis.models import SearchHistory
from analysis.services.analyze_coordinates.search_all import SearchAll
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.view_services.result_map_formatter import (
    format_data_map,
    planet_tiles_url,
)
from analysis.services.view_services.bases_3d import (
    MAX_TILE_ZOOM,
    MUNICIPIOS_JSON,
    bases_summary,
    cities_summary,
    render_tile,
)
from analysis.services.view_services.zip_upload_service import ZipUploadService
from analysis.services.view_services.kmz_points_service import (
    KmzPointsError,
    car_details,
    car_perimeters,
    locate_cars,
    locate_municipalities,
    parse_location_points,
    summarize_cars,
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
        SearchHistory.objects.create(
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
    except Exception:
        pass


class HomePageView(View):
    template_name = 'analysis/home.html'

    def get(self, request):
        return render(request, self.template_name)

class ResultsPageView(View):
    template_name = 'analysis/results.html'

    def get(self, request):
        data = request.session.get('last_analysis') or {}
        data['planet_tiles_url'] = planet_tiles_url()
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
            resultado = SearchAll().execute(coordenadas_input)

            municipio, uf = None, None
            try:
                municipio, uf = locate_city_state(coordenadas_input)
            except Exception:
                pass

            data = {
                'resultado': resultado,
                'coordenadas_recebidas': coordenadas_input,
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
                'coordenadas_recebidas': coordenadas_input,
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
            'planet_tiles_url': planet_tiles_url()
        })

class HistoricoView(View):
    """Lista as buscas que o próprio usuário logado já realizou."""
    template_name = 'analysis/historico.html'

    def get(self, request):
        historico_qs = SearchHistory.objects.filter(user=request.user)

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

        context = {
            'page_obj': page_obj,
            'total_buscas': SearchHistory.objects.filter(user=request.user).count(),
            'search_types': SearchHistory.SearchType.choices,
            'filtro_tipo': filtro_tipo,
            'busca_texto': busca_texto,
        }
        return render(request, self.template_name, context)


class HistoricoDetalheView(View):
    """Reabre o resultado de uma busca do próprio usuário logado."""

    def get(self, request, pk):
        historico = get_object_or_404(SearchHistory, pk=pk, user=request.user)

        data = dict(historico.result_data or {})
        data['planet_tiles_url'] = planet_tiles_url()
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
        data = request.session.get('last_analysis') or {}
        data = self.format_data(data)
        return render(request, self.template_name, data)

    def format_data(self, data: dict) -> dict:
        resultado = data.get('resultado') or {}
        data['has_mapbiomas_alerts'] = False
        
        # Calcular área total por base
        if resultado and 'resultados_por_base' in resultado:
            for base in resultado['resultados_por_base']:
                # Filter out water bodies from Fitoecologias
                if "Fitoecologias" in base.get('nome_base', ''):
                    base['areas_encontradas'] = [
                        item for item in base.get('areas_encontradas', [])
                        if not ("água" in item.get('item_info', '').lower() or "agua" in item.get('item_info', '').lower())
                    ]

                areas = base.get('areas_encontradas', [])
                total = 0.0
                for item in areas:
                    try:
                        total += float(item.get('area', 0))
                    except (ValueError, TypeError):
                        pass
                base['total_area'] = total

                nome_base = base.get('nome_base', '')
                if (
                    ("Mapbiomas" in nome_base or "MapBiomas" in nome_base)
                    and base.get('areas_encontradas')
                ):
                    data['has_mapbiomas_alerts'] = True

        demonstrativo = data.get('demonstrativo')

        if not demonstrativo:
            return data

        area_rl_proposta = demonstrativo.get('area_reserva_legal_proposta_num', 0)
        area_preservada_calculada = resultado.get('area_preservada_total', 0)

        deficit_rl = area_rl_proposta - area_preservada_calculada

        data['has_deficit_rl'] = deficit_rl < 0
        data['deficit_rl_value'] = f"{(deficit_rl):.4f} ha"

        return data


class DownloadPropertyShapefileView(View):
    def get(self, request):
        data = request.session.get('last_analysis') or {}
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
        data = request.session.get('last_analysis') or {}
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
        'bases': bases_summary(),
        'cities': cities_summary(),
    }


class UploadZipCarView(View):
    """Página inicial depois do login: mapa 3D do SICAR com o tour de cidade
    em cidade e o formulário de análise no canto."""
    template_upload = 'analysis/bases_3d.html'
    template_index = 'analysis/results.html'

    def get(self, request):
        return self._render_form(request, {})

    def _render_form(self, request, context):
        context['bases_3d_config'] = _bases_3d_config(request)
        return render(request, self.template_upload, context)

    def post(self, request):
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

        except Exception as e:
            context['erro'] = f'Erro ao processar o arquivo: {str(e)}'
            return self._render_form(request, context)

    # =====================================================================
    # Métodos auxiliares
    # =====================================================================

    def _get_car_data(self, car_number):
        """Busca dados do CAR e localidade."""
        resultado = {}
        municipio, state = None, None
        
        if car_number:
            try:
                resultado = SearchForCar().execute(car_number) or {}
                qs = get_sicar_record(car_number__iexact=car_number)
                if qs.exists():
                    geometry = qs.first().geometry
                    municipio, state = locate_city_state(geometry)
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
            parser = DocumentsParserFactory.create_parser(doc_type)
            extractor = ExtractDocumentPdfPlumber()
            ctx = DocumentDataContext(extractor, parser)
            info = ctx.extract_data(file_obj)
            
            car_extraido = (info.car or car_input or '').strip()

            resultado, municipio, state = self._get_car_data(car_extraido)

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

        except Exception as e:
            context['erro'] = f'{error_prefix}: {str(e)}'
            return self._render_form(request, context)

    def _handle_only_car(self, request, car_input, context):
        """Processa requisição apenas com o CAR (sem ZIP)."""
        try:
            resultado, municipality, state = self._get_car_data(car_input)

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

        except Exception as e:
            context['erro'] = f'Erro ao analisar pelo CAR: {str(e)}'
            return self._render_form(request, context)

    def _process_coordinates(self, request, coordenadas_input, car_input):
        """Processa os dados extraídos do shapefile."""
        try:
            resultado = SearchAll().execute(coordenadas_input)
            municipio, uf = None, None
            try:
                municipio, uf = locate_city_state(coordenadas_input)
            except Exception:
                pass
            data = {
                'resultado': resultado,
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'municipio': municipio,
                'uf': uf,
                'sucesso': True
            }
            _save_search_history(request, data, SearchHistory.SearchType.SHAPEFILE)
            request.session['last_analysis'] = data
            return redirect('results')
        except Exception as e:
            data = {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': coordenadas_input,
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
            locate_cars(points)
        except KmzPointsError as e:
            return render(request, self.template_name, {'erro': str(e)})
        except Exception as e:
            return render(request, self.template_name, {'erro': f'Erro ao processar os arquivos: {e}'})

        try:
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
        except Exception:
            details = {}
        municipios = _municipios_por_codigo()

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
                    # Posições dos CARs em `map_cars`.
                    'cars': [car_position[c['car_number']] for c in p.cars],
                }
                for p in points
            ],
            'map_sources': sources,
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


def termos(request):
    return render(request, 'analysis/termos_de_uso.html')


class BaseTileView(View):
    """Vector tile (MVT) de uma base, recortado pelo Tocantins."""

    def get(self, request, modelo, z, x, y):
        tile = render_tile(modelo, z, x, y)
        if not tile:
            return HttpResponse(status=204)
        response = HttpResponse(tile, content_type='application/vnd.mapbox-vector-tile')
        response['Cache-Control'] = 'private, max-age=3600'
        return response
