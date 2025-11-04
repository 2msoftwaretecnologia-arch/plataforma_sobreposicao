from django.shortcuts import render
from django.conf import settings
from core.actions_files import fazer_busca_completa
from helpers.extact_cordinates import extrair_cordenadas
import zipfile
import os


def homepage(request):
    if request.method == 'POST':
        
        coordenadas_input = "POLYGON ((-49.61488861 -9.2536925, -49.61271028 -9.26027167, -49.61269 -9.26039417, -49.60878389 -9.2774275, -49.6255502997 -9.28127610719, -49.62119583 -9.26671, -49.62675194 -9.25840667, -49.61488861 -9.2536925))"
                            
        car_input = request.POST.get('car_input', '').strip()
        
        if coordenadas_input.strip():
            try:
                
                # Chama a função de busca completa em todas as bases
                resultado = fazer_busca_completa(coordenadas_input, car_input)
                
                return render(request, 'homepage/index.html', {
                    'resultado': resultado,
                    'coordenadas_recebidas': coordenadas_input,
                    'car_input': car_input,
                    'sucesso': True
                })
            except Exception as e:
                return render(request, 'homepage/index.html', {
                    'erro': f'Erro ao processar coordenadas: {str(e)}',
                    'coordenadas_recebidas': coordenadas_input,
                    'car_input': car_input,
                    'sucesso': False
                })
        else:
            return render(request, 'homepage/index.html', {
                'erro': 'Por favor, insira coordenadas válidas.',
                'sucesso': False
            })
    
    return render(request, 'homepage/index.html')


def upload_zip_car(request):
    if request.method == 'POST':
        zip_file = request.FILES.get('zip_file')
        car_input = request.POST.get('car_input', '').strip()

        context = { 'car_input': car_input }

        if not zip_file:
            context['erro'] = 'Por favor, envie um arquivo ZIP.'
            return render(request, 'homepage/upload.html', context)

        try:
            # Diretório de uploads
            uploads_dir = os.path.join(settings.BASE_DIR, 'uploads')
            os.makedirs(uploads_dir, exist_ok=True)

            # Salvar ZIP temporariamente em uploads
            temp_zip_path = os.path.join(uploads_dir, f"upload_tmp_{zip_file.name}")

            with open(temp_zip_path, 'wb') as f:
                for chunk in zip_file.chunks():
                    f.write(chunk)

            # Extrair conteúdo do ZIP para uploads
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(uploads_dir)

            # Remover ZIP temporário
            try:
                os.remove(temp_zip_path)
            except OSError:
                pass

            # Localizar o primeiro arquivo .shp extraído
            shp_path = None
            for root, _, files in os.walk(uploads_dir):
                for fname in files:
                    if fname.lower().endswith('.shp'):
                        shp_path = os.path.join(root, fname)
                        break
                if shp_path:
                    break

            if not shp_path:
                context['erro'] = 'Nenhum arquivo .shp encontrado no ZIP.'
                return render(request, 'homepage/upload.html', context)

            # Extrair coordenadas do shapefile encontrado
            coordenadas_input = extrair_cordenadas(shp_path)
            if not coordenadas_input or not str(coordenadas_input).strip():
                context['erro'] = 'Não foi possível extrair coordenadas do shapefile enviado.'
                return render(request, 'homepage/upload.html', context)

            # Processar e retornar à homepage com os resultados
            try:
                resultado = fazer_busca_completa(coordenadas_input, car_input)
                return render(request, 'homepage/index.html', {
                    'resultado': resultado,
                    'coordenadas_recebidas': coordenadas_input,
                    'car_input': car_input,
                    'sucesso': True
                })
            except Exception as e:
                return render(request, 'homepage/index.html', {
                    'erro': f'Erro ao processar coordenadas: {str(e)}',
                    'coordenadas_recebidas': coordenadas_input,
                    'car_input': car_input,
                    'sucesso': False
                })

        except zipfile.BadZipFile:
            context['erro'] = 'Arquivo ZIP inválido ou corrompido.'
            return render(request, 'homepage/upload.html', context)
        except Exception as e:
            context['erro'] = f'Erro ao processar o arquivo: {str(e)}'
            return render(request, 'homepage/upload.html', context)

    return render(request, 'homepage/upload.html')
