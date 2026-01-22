# Standard library
import zipfile
from dataclasses import asdict

# Django
from django.conf import settings
from django.shortcuts import redirect, render
from django.views import View

# Local apps – analysis
from analysis.services.analyze_coordinates.search_all import SearchAll
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.view_services.zip_upload_service import ZipUploadService

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


class HomePageView(View):
    template_name = 'analysis/home.html'

    def get(self, request):
        return render(request, self.template_name)

class ResultsPageView(View):
    template_name = 'analysis/results.html'

    def get(self, request):
        data = request.session.get('last_analysis') or {}
        data['planet_tiles_url'] = self._planet_tiles_url()
        data = self._format_data_map(data)
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
            request.session['last_analysis'] = data
            return redirect('results')

        except Exception as e:
            data = {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'sucesso': False
            }
            request.session['last_analysis'] = data
            return redirect('results')

    def _render_error(self, request, message, car_input=None):
        return render(request, self.template_name, {
            'erro': message,
            'car_input': car_input,
            'sucesso': False,
            'planet_tiles_url': self._planet_tiles_url()
        })

    def _planet_tiles_url(self):
        try:
            mosaic = getattr(settings, 'PLANET_BASEMAP_MOSAIC', '')
            key = getattr(settings, 'PLANET_API_KEY', '')
            if mosaic and key:
                return f"https://tiles.planet.com/basemaps/v1/planet-tiles/{mosaic}/gmap/{{z}}/{{x}}/{{y}}.png?api_key={key}"
        except Exception:
            pass
        return ''

    def _format_data_map(self, data):
        resultado = data.get('resultado')
        items = [
            {
                "gj": resultado["alvo_geojson"],
                "label": "Área da Propriedade",
                "area": f'{resultado["tamanho_area"]:.4f} ha',
                "color": "#000000",
                "fonte": "Área da Propriedade",
            }
        ]

        for p in resultado["poligonos_imoveis"]:
            items.append({
                "gj": p["polygon_geojson"],
                "label": p["item_info"],
                "area": f'{p["area"]:.4f} ha',
                "color": p["color"],
                "fonte": p["fonte"],
            })

        data['map_items'] = items
        return data
class ReportPrintView(View):
    template_name = 'analysis/report_print.html'

    def get(self, request):
        data = request.session.get('last_analysis') or {}
        data = self.format_data(data)
        return render(request, self.template_name, data)

    def format_data(self, data: dict) -> dict:
        resultado = data.get('resultado')
        demonstrativo = data.get('demonstrativo')

        if not demonstrativo:
            return data

        area_rl_proposta = demonstrativo.get('area_reserva_legal_proposta_num', 0)
        area_preservada_calculada = resultado.get('area_preservada_total', 0)

        deficit_rl = area_rl_proposta - area_preservada_calculada

        data['has_deficit_rl'] = deficit_rl < 0
        data['deficit_rl_value'] = f"{(deficit_rl):.4f} ha"

        return data

class UploadZipCarView(View):
    template_upload = 'analysis/upload.html'
    template_index = 'analysis/results.html'
    
    def get(self, request):
        return render(request, self.template_upload)

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
        # 1) Caso só CAR informado (sem ZIP)
        # --------------------------------------
        if not zip_file and car_input:
            return self._handle_only_car(request, car_input, context)

        # --------------------------------------
        # 2) Nenhum arquivo enviado
        # --------------------------------------
        if not zip_file:
            context['erro'] = 'Por favor, envie um arquivo ZIP ou informe o número do CAR.'
            return render(request, self.template_upload, context)

        # --------------------------------------
        # 3) Caso ZIP enviado
        # --------------------------------------
        try:
            zip_dataframe = ZipUploadService().extract_geodataframe(zip_file)

            if zip_dataframe is None or zip_dataframe.empty:
                context['erro'] = 'O arquivo ZIP não contém dados geográficos válidos.'
                return render(request, self.template_upload, context)

            coordenadas_input = extract_geometry(zip_dataframe)

            if not coordenadas_input or not str(coordenadas_input).strip():
                context['erro'] = 'Não foi possível extrair coordenadas do shapefile enviado.'
                return render(request, self.template_upload, context)

            return self._process_coordinates(request, coordenadas_input, car_input)

        except zipfile.BadZipFile:
            context['erro'] = 'Arquivo ZIP inválido ou corrompido.'
            return render(request, self.template_upload, context)

        except Exception as e:
            context['erro'] = f'Erro ao processar o arquivo: {str(e)}'
            return render(request, self.template_upload, context)

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

    def _handle_document_upload(self, request, file_obj, doc_type, result_key, car_input, missing_msg, error_prefix, context):
        """Processa upload de documentos (Recibo ou Demonstrativo)."""
        if not file_obj:
            context['erro'] = missing_msg
            return render(request, self.template_upload, context)

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

            import json

            with open("car_data.json", "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            request.session['last_analysis'] = data
            return redirect('results')
        except Exception as e:
            context['erro'] = f'{error_prefix}: {str(e)}'
            return render(request, self.template_upload, context)

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
            request.session['last_analysis'] = data
            return redirect('results')

        except Exception as e:
            context['erro'] = f'Erro ao analisar pelo CAR: {str(e)}'
            return render(request, self.template_upload, context)

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
            request.session['last_analysis'] = data
            return redirect('results')
        except Exception as e:
            data = {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'sucesso': False
            }
            request.session['last_analysis'] = data
            return redirect('results')

def termos(request):
    return render(request, 'analysis/termos_de_uso.html')
