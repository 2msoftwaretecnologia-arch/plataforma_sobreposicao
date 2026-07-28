from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .custom_layer_importer import CustomLayerImporter
from .models import CustomLayer, CustomLayerColumn, CustomLayerFeature
from .tasks import process_custom_layer_task


@require_POST
def custom_layer_create_view(request):
    nome = (request.POST.get('nome') or '').strip()
    cor = (request.POST.get('cor') or '#607D8B').strip()
    arquivo = request.FILES.get('arquivo')

    if not nome:
        messages.error(request, "Informe um nome para a nova base.")
        return redirect('control_panel:bases_dados')
    if not arquivo:
        messages.error(request, "Envie um arquivo .zip com o shapefile da nova base.")
        return redirect('control_panel:bases_dados')
    if not arquivo.name.lower().endswith('.zip'):
        messages.error(request, "O arquivo precisa ser um .zip contendo o shapefile (.shp, .dbf, .shx, ...).")
        return redirect('control_panel:bases_dados')

    layer = CustomLayer.objects.create(
        nome=nome, cor=cor, arquivo=arquivo, created_by=request.user,
    )
    messages.success(request, f"Base \"{nome}\" criada. Agora escolha quais colunas devem aparecer.")
    return redirect('control_panel:custom_layer_columns', layer_id=layer.id)


def custom_layer_columns_view(request, layer_id):
    layer = get_object_or_404(CustomLayer, id=layer_id)

    if request.method == 'POST':
        nomes_enviados = request.POST.getlist('coluna_origem')
        for ordem, coluna_origem in enumerate(nomes_enviados):
            rotulo = (request.POST.get(f'rotulo_{coluna_origem}') or coluna_origem).strip() or coluna_origem
            incluir = bool(request.POST.get(f'incluir_{coluna_origem}'))
            CustomLayerColumn.objects.update_or_create(
                layer=layer, coluna_origem=coluna_origem,
                defaults={'rotulo': rotulo, 'incluir': incluir, 'ordem': ordem},
            )
        messages.success(request, f"Colunas de \"{layer.nome}\" atualizadas. Agora clique em \"Processar\" para importar os dados.")
        return redirect('control_panel:bases_dados')

    existentes = {c.coluna_origem: c for c in layer.colunas.all()}
    try:
        descobertas = CustomLayerImporter(layer).discover_columns()
    except Exception as e:
        messages.error(request, f"Não foi possível ler as colunas do arquivo enviado: {e}")
        descobertas = []

    colunas_exibir = []
    vistos = set()
    for coluna_origem in descobertas:
        vistos.add(coluna_origem)
        existente = existentes.get(coluna_origem)
        colunas_exibir.append({
            'coluna_origem': coluna_origem,
            'rotulo': existente.rotulo if existente else coluna_origem,
            'incluir': existente.incluir if existente else True,
            'ausente_no_arquivo': False,
        })

    for coluna_origem, existente in existentes.items():
        if coluna_origem not in vistos:
            colunas_exibir.append({
                'coluna_origem': coluna_origem,
                'rotulo': existente.rotulo,
                'incluir': existente.incluir,
                'ausente_no_arquivo': True,
            })

    return render(request, 'control_panel/custom_layer_colunas.html', {
        'active_nav': 'bases_dados',
        'layer': layer,
        'colunas': colunas_exibir,
    })


@require_POST
def custom_layer_upload_view(request, layer_id):
    layer = get_object_or_404(CustomLayer, id=layer_id)
    arquivo = request.FILES.get('arquivo')

    if not arquivo:
        messages.error(request, "Nenhum arquivo selecionado.")
        return redirect('control_panel:bases_dados')
    if not arquivo.name.lower().endswith('.zip'):
        messages.error(request, "O arquivo precisa ser um .zip contendo o shapefile.")
        return redirect('control_panel:bases_dados')

    layer.arquivo = arquivo
    layer.save()
    messages.success(request, f"Novo arquivo enviado para \"{layer.nome}\". Revise as colunas antes de processar.")
    return redirect('control_panel:custom_layer_columns', layer_id=layer.id)


@require_POST
def custom_layer_importar_view(request, layer_id):
    layer = get_object_or_404(CustomLayer, id=layer_id)

    process_custom_layer_task.delay(layer.id, request.user.id if request.user.is_authenticated else None)
    messages.success(
        request,
        f"Processamento de \"{layer.nome}\" iniciado em segundo plano. "
        "Atualize esta página em alguns instantes para conferir os dados importados."
    )

    return redirect('control_panel:bases_dados')


@require_POST
def custom_layer_ativar_view(request, layer_id):
    layer = get_object_or_404(CustomLayer, id=layer_id)

    if not layer.ativo and not layer.features.exists():
        messages.error(request, f"Importe os dados de \"{layer.nome}\" antes de ativar.")
        return redirect('control_panel:bases_dados')

    layer.ativo = not layer.ativo
    layer.save(update_fields=['ativo', 'updated_at'])

    if layer.ativo:
        messages.success(request, f"\"{layer.nome}\" ativada — já entra nas próximas buscas de sobreposição.")
    else:
        messages.success(request, f"\"{layer.nome}\" desativada — não aparece mais nas buscas de sobreposição.")

    return redirect('control_panel:bases_dados')


@require_POST
def custom_layer_excluir_view(request, layer_id):
    layer = get_object_or_404(CustomLayer, id=layer_id)
    nome = layer.nome

    if layer.arquivo:
        layer.arquivo.delete(save=False)
    layer.delete()  # cascade: apaga CustomLayerColumn e CustomLayerFeature dessa base

    messages.success(request, f"Base customizada \"{nome}\" excluída.")
    return redirect('control_panel:bases_dados')
