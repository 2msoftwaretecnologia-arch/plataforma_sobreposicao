from django.shortcuts import render
from core.actions_files import fazer_busca_completa

def homepage(request):
    if request.method == 'POST':
        coordenadas_input = request.POST.get('coordenadas_input', '')
        excluir_car = request.POST.get('excluir_car', '').strip()
        
        if coordenadas_input.strip():
            try:
                
                # Chama a função de busca completa em todas as bases
                resultado = fazer_busca_completa(coordenadas_input, excluir_car)
                
                return render(request, 'homepage/index.html', {
                    'resultado': resultado,
                    'coordenadas_recebidas': coordenadas_input,
                    'excluir_car': excluir_car,
                    'sucesso': True
                })
            except Exception as e:
                return render(request, 'homepage/index.html', {
                    'erro': f'Erro ao processar coordenadas: {str(e)}',
                    'coordenadas_recebidas': coordenadas_input,
                    'excluir_car': excluir_car,
                    'sucesso': False
                })
        else:
            return render(request, 'homepage/index.html', {
                'erro': 'Por favor, insira coordenadas válidas.',
                'sucesso': False
            })
    
    return render(request, 'homepage/index.html')
