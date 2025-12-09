from django.shortcuts import render
from analysis.services.analyze_coordinates.search_all import SearchAll
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.view_services.zip_upload_service import ZipUploadService
from car_system.utils import get_sicar_record
import zipfile
from kernel.utils import extract_geometry, locate_city_state


from django.views import View
from django.shortcuts import render
from dataclasses import asdict
from extract_text_from_pdf import extrair_texto_pdf_pdfplumber
from extract_datas_demostrativo import parse_demonstrativo
from extract_datas_recibo import extrair_recibo_info

class AnswerspageView(View):
    template_name = 'analysis/index.html'

    def get(self, request):
        """Exibe a página inicial."""
        return render(request, self.template_name)

    def post(self, request):
        """Processa o envio das coordenadas via POST."""
        coordenadas_input = extract_geometry()
        car_input = request.POST.get('car_input', '').strip()

        if not coordenadas_input or not str(coordenadas_input).strip():
            return self._render_error(request, 'Por favor, insira coordenadas válidas.', car_input)

        return self._process_coordinates(request, coordenadas_input, car_input)

    # =====================================================================
    # Métodos auxiliares (Clean Code)
    # =====================================================================

    def _process_coordinates(self, request, coordenadas_input, car_input):
        """Executa a pesquisa nas bases e retorna o resultado."""
        try:
            resultado = SearchAll().execute(coordenadas_input, car_input)

            return render(request, self.template_name, {
                'resultado': resultado,
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'sucesso': True
            })

        except Exception as e:
            return render(request, self.template_name, {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'sucesso': False
            })

    def _render_error(self, request, message, car_input=None):
        return render(request, self.template_name, {
            'erro': message,
            'car_input': car_input,
            'sucesso': False
        })

class UploadZipCarView(View):
    template_upload = 'analysis/upload.html'
    template_index = 'analysis/index.html'
    
    def get(self, request):
        return render(request, self.template_upload)

    def post(self, request):
        zip_file = request.FILES.get('zip_file')
        car_input = request.POST.get('car_input', '').strip()
        mode = request.POST.get('mode', '').strip()

        context = {'car_input': car_input}

        if mode == 'demostrativo':
            demo_file = request.FILES.get('demo_file')
            if not demo_file:
                context['erro'] = 'Por favor, envie um arquivo PDF do demonstrativo.'
                return render(request, self.template_upload, context)

            try:
                texto = extrair_texto_pdf_pdfplumber(demo_file)
                info = parse_demonstrativo(texto)
                car_extraido = (info.car or car_input or '').strip()

                resultado = {}
                municipio, state = None, None

                if car_extraido:
                    try:
                        resultado = SearchForCar().execute(car_extraido) or {}
                        qs = get_sicar_record(car_number__iexact=car_extraido)
                        if qs.exists():
                            geometry = qs.first().geometry
                            municipio, state = locate_city_state(geometry)
                    except Exception:
                        pass

                return render(request, self.template_index, {
                    'resultado': resultado,
                    'demonstrativo': asdict(info),
                    'car_input': car_extraido,
                    'municipio': municipio,
                    'uf': state,
                    'sucesso': True
                })
            except Exception as e:
                context['erro'] = f'Erro ao processar o demonstrativo: {str(e)}'
                return render(request, self.template_upload, context)

        elif mode == 'recibo':
            recibo_file = request.FILES.get('recibo_file')
            if not recibo_file:
                context['erro'] = 'Por favor, envie um arquivo PDF do recibo.'
                return render(request, self.template_upload, context)

            try:
                info = extrair_recibo_info(recibo_file)
                car_extraido = (info.car or car_input or '').strip()

                resultado = {}
                municipio, state = None, None

                if car_extraido:
                    try:
                        resultado = SearchForCar().execute(car_extraido) or {}
                        qs = get_sicar_record(car_number__iexact=car_extraido)
                        if qs.exists():
                            geometry = qs.first().geometry
                            municipio, state = locate_city_state(geometry)
                    except Exception:
                        pass

                return render(request, self.template_index, {
                    'resultado': resultado,
                    'recibo': asdict(info),
                    'car_input': car_extraido,
                    'municipio': municipio,
                    'uf': state,
                    'sucesso': True
                })
            except Exception as e:
                context['erro'] = f'Erro ao processar o recibo: {str(e)}'
                return render(request, self.template_upload, context)

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

    def _handle_only_car(self, request, car_input, context):
        """Processa requisição apenas com o CAR (sem ZIP)."""
        try:
            resultado = SearchForCar().execute(car_input)

            municipality, state = None, None
            wkt_car = get_sicar_record(car_number__iexact=car_input)

            if wkt_car.exists():
                geometry = wkt_car.first().geometry
                municipality, state = locate_city_state(geometry)

            return render(request, self.template_index, {
                'resultado': resultado,
                'car_input': car_input,
                'municipio': municipality,
                'uf': state,
                'sucesso': True
            })

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

            return render(request, self.template_index, {
                'resultado': resultado,
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'municipio': municipio,
                'uf': uf,
                'sucesso': True
            })

        except Exception as e:
            return render(request, self.template_index, {
                'erro': f'Erro ao processar coordenadas: {str(e)}',
                'coordenadas_recebidas': coordenadas_input,
                'car_input': car_input,
                'sucesso': False
            })

def termos(request):
    return render(request, 'analysis/termos_de_uso.html')
