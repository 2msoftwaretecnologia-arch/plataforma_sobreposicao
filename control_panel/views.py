from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from analysis.models import SearchHistory
from analysis.services.view_services.result_map_formatter import (
    format_data_map,
    planet_tiles_url,
)
from kernel.utils import cached_model_count, reset_db

from . import utils
from .bases_config import BASES_CONFIG, get_bases_config, get_toggleable_fields
from .column_toggle_service import get_active_map_for_layer, set_field_active
from .layer_registry import LAYER_REGISTRY
from .models import CustomLayer
from .tasks import process_layer_task

CHART_WIDTH = 640
CHART_HEIGHT = 200
CHART_PADDING = 30


def _fnum(value):
    """Plain-string number formatting, immune to pt-br locale comma substitution
    when interpolated into CSS/SVG attributes."""
    return f"{round(value, 1):g}"


def _build_chart(snapshots):
    if len(snapshots) < 2:
        return None

    points = []
    usable_width = CHART_WIDTH - 2 * CHART_PADDING
    step = usable_width / (len(snapshots) - 1)

    for index, snapshot in enumerate(snapshots):
        percent = (snapshot.disk_used_bytes / snapshot.disk_total_bytes) * 100
        x = CHART_PADDING + index * step
        y = CHART_PADDING + (100 - percent) / 100 * (CHART_HEIGHT - 2 * CHART_PADDING)
        points.append({
            'x': _fnum(x),
            'y': _fnum(y),
            'label_y': CHART_HEIGHT - 8,
            'label': snapshot.captured_at.strftime('%d/%m'),
            'percent': _fnum(percent),
        })

    polyline = ' '.join(f"{p['x']},{p['y']}" for p in points)

    def y_for_percent(percent):
        return _fnum(CHART_PADDING + (100 - percent) / 100 * (CHART_HEIGHT - 2 * CHART_PADDING))

    return {
        'width': CHART_WIDTH,
        'height': CHART_HEIGHT,
        'points': points,
        'polyline': polyline,
        'warning_y': y_for_percent(70),
        'critical_y': y_for_percent(90),
    }


def _build_top_tables():
    rows = utils.get_top_tables()
    if not rows:
        return []

    max_size = rows[0][1] or 1
    return [
        {
            'name': name,
            'size': utils.format_bytes(size_bytes),
            'bar_percent': _fnum((size_bytes / max_size) * 100),
        }
        for name, size_bytes in rows
    ]


def _storage_context(snapshot):
    percent = (snapshot.disk_used_bytes / snapshot.disk_total_bytes) * 100
    status_code, status_label = utils.get_storage_status(percent)

    return {
        'database_size': utils.format_bytes(snapshot.database_size_bytes),
        'disk_used': utils.format_bytes(snapshot.disk_used_bytes),
        'disk_total': utils.format_bytes(snapshot.disk_total_bytes),
        'hostname': snapshot.hostname,
        'percent': _fnum(percent),
        'status_code': status_code,
        'status_label': status_label,
        'last_updated': snapshot.captured_at,
        'chart': _build_chart(utils.get_last_7_days_snapshots()),
        'top_tables': _build_top_tables(),
    }


def dashboard_home_view(request):
    return redirect(reverse('control_panel:armazenamento'))


def armazenamento_view(request):
    snapshot = utils.get_or_refresh_latest_snapshot()
    context = _storage_context(snapshot)
    context['active_nav'] = 'armazenamento'
    return render(request, 'control_panel/armazenamento.html', context)


@require_POST
def armazenamento_refresh_view(request):
    utils.capture_storage_snapshot()
    messages.success(request, "Métricas de armazenamento atualizadas.")
    return redirect(reverse('control_panel:armazenamento'))


def usuarios_view(request):
    usuarios_qs = User.objects.select_related('profile').order_by('-date_joined')
    paginator = Paginator(usuarios_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'active_nav': 'usuarios',
        'usuarios': page_obj,
        'page_obj': page_obj,
        'total_usuarios': paginator.count,
    }
    return render(request, 'control_panel/usuarios.html', context)


def buscas_view(request):
    buscas_qs = SearchHistory.objects.select_related('user')

    filtro_tipo = request.GET.get('tipo', '').strip()
    if filtro_tipo:
        buscas_qs = buscas_qs.filter(search_type=filtro_tipo)

    filtro_erros = request.GET.get('erros') == '1'
    if filtro_erros:
        buscas_qs = buscas_qs.filter(sucesso=False)

    busca_texto = request.GET.get('q', '').strip()
    if busca_texto:
        buscas_qs = buscas_qs.filter(
            Q(car_input__icontains=busca_texto)
            | Q(municipio__icontains=busca_texto)
            | Q(user__username__icontains=busca_texto)
        )

    paginator = Paginator(buscas_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'active_nav': 'buscas',
        'page_obj': page_obj,
        'total_buscas': SearchHistory.objects.count(),
        'total_sucesso': SearchHistory.objects.filter(sucesso=True).count(),
        'total_erros': SearchHistory.objects.filter(sucesso=False).count(),
        'search_types': SearchHistory.SearchType.choices,
        'filtro_tipo': filtro_tipo,
        'filtro_erros': filtro_erros,
        'busca_texto': busca_texto,
    }
    return render(request, 'control_panel/buscas.html', context)


def busca_detalhe_view(request, pk):
    historico = get_object_or_404(SearchHistory.objects.select_related('user'), pk=pk)

    data = dict(historico.result_data or {})
    data['planet_tiles_url'] = planet_tiles_url()
    data = format_data_map(data)
    data['is_historico'] = True
    data['historico'] = historico
    data['historico_back_url'] = reverse('control_panel:buscas')
    data['historico_back_label'] = 'Voltar para Buscas'
    data['historico_eyebrow'] = 'Histórico de busca — painel administrativo'

    return render(request, 'analysis/results.html', data)


def _get_base_cfg(modelo):
    base_cfg = next((b for b in BASES_CONFIG if b['modelo'] == modelo), None)
    if base_cfg is None or modelo not in LAYER_REGISTRY:
        raise Http404(f"Base '{modelo}' não encontrada.")
    return base_cfg


def _file_info(file_mgmt, field_name):
    file_field = getattr(file_mgmt, field_name, None) if file_mgmt else None
    if not file_field:
        return None, None
    try:
        return file_field.name.rsplit('/', 1)[-1], utils.format_bytes(file_field.size)
    except (FileNotFoundError, OSError, ValueError):
        return file_field.name.rsplit('/', 1)[-1], None


def bases_dados_view(request):
    bases = get_bases_config()
    file_mgmt = utils.get_file_management()
    for base in bases:
        base['total_registros'] = cached_model_count(LAYER_REGISTRY[base['modelo']]['model'])
        base['arquivo_nome'], base['arquivo_tamanho'] = _file_info(file_mgmt, base['arquivo_upload'])

        if base['total_registros'] > 0:
            base['status_code'] = 'ok'
            base['status_label'] = f"{base['total_registros']} registros importados"
        elif base['arquivo_nome']:
            base['status_code'] = 'pendente'
            base['status_label'] = "Arquivo enviado, aguardando processamento"
        else:
            base['status_code'] = 'vazio'
            base['status_label'] = "Sem arquivo e sem dados"

        campos_saida = [c['saida'] for c in base['colunas_extraidas'] if c.get('saida')]
        estado = get_active_map_for_layer(base['modelo'], campos_saida)
        # Novas dicts (não mutar os itens de BASES_CONFIG, que são compartilhados
        # entre requisições) só para anotar o estado ligado/desligado de cada coluna.
        base['colunas_extraidas'] = [
            {**coluna, 'ativo': estado.get(coluna['saida']) if coluna.get('saida') else None}
            for coluna in base['colunas_extraidas']
        ]
        base['tem_colunas_togglable'] = len(campos_saida) > 0

    context = {
        'active_nav': 'bases_dados',
        'bases': bases,
        'total_bases': len(bases),
        'total_colunas': sum(b['total_colunas'] for b in bases),
        'custom_layers': _build_custom_layers_context(),
    }
    return render(request, 'control_panel/bases_dados.html', context)


def _build_custom_layers_context():
    custom_layers = []
    layers_qs = (
        CustomLayer.objects
        .prefetch_related('colunas')
        .annotate(total_features=Count('features', distinct=True))
    )
    for layer in layers_qs:
        colunas = list(layer.colunas.all())
        total_features = layer.total_features

        if not layer.arquivo:
            status_code, status_label = 'vazio', "Sem arquivo enviado"
        elif not colunas:
            status_code, status_label = 'pendente', "Aguardando definição de colunas"
        elif total_features == 0:
            status_code, status_label = 'pendente', "Colunas definidas, aguardando processamento"
        elif not layer.ativo:
            status_code, status_label = 'revisao', f"{total_features} feições importadas — aguardando ativação"
        else:
            status_code, status_label = 'ok', f"{total_features} feições — ativa nas buscas de sobreposição"

        arquivo_nome, arquivo_tamanho = None, None
        if layer.arquivo:
            try:
                arquivo_nome = layer.arquivo.name.rsplit('/', 1)[-1]
                arquivo_tamanho = utils.format_bytes(layer.arquivo.size)
            except (FileNotFoundError, OSError, ValueError):
                arquivo_nome = layer.arquivo.name.rsplit('/', 1)[-1]

        custom_layers.append({
            'layer': layer,
            'colunas': colunas,
            'total_colunas': len(colunas),
            'total_incluidas': sum(1 for c in colunas if c.incluir),
            'total_features': total_features,
            'status_code': status_code,
            'status_label': status_label,
            'arquivo_nome': arquivo_nome,
            'arquivo_tamanho': arquivo_tamanho,
        })
    return custom_layers


@require_POST
def base_upload_view(request, modelo):
    base_cfg = _get_base_cfg(modelo)

    arquivo = request.FILES.get('arquivo')
    if not arquivo:
        messages.error(request, "Nenhum arquivo selecionado.")
        return redirect('control_panel:bases_dados')
    if not arquivo.name.lower().endswith('.zip'):
        messages.error(request, "O arquivo precisa ser um .zip contendo o shapefile (.shp, .dbf, .shx, ...).")
        return redirect('control_panel:bases_dados')

    file_mgmt = utils.get_file_management()
    if file_mgmt is None:
        messages.error(request, "Nenhum registro de Gerenciamento de Arquivos existe ainda. Crie um em /admin/ primeiro.")
        return redirect('control_panel:bases_dados')

    setattr(file_mgmt, base_cfg['arquivo_upload'], arquivo)
    file_mgmt.save()
    messages.success(
        request,
        f"Arquivo enviado para \"{base_cfg['nome_base']}\". Clique em \"Processar\" para importar os dados."
    )
    return redirect('control_panel:bases_dados')


@require_POST
def base_processar_view(request, modelo):
    base_cfg = _get_base_cfg(modelo)

    process_layer_task.delay(modelo, request.user.id if request.user.is_authenticated else None)
    messages.success(
        request,
        f"Processamento de \"{base_cfg['nome_base']}\" iniciado em segundo plano. "
        "Atualize esta página em alguns instantes para ver o resultado."
    )

    return redirect('control_panel:bases_dados')


@require_POST
def base_toggle_fields_view(request, modelo):
    base_cfg = _get_base_cfg(modelo)
    togglable = get_toggleable_fields(modelo)

    for campo_cfg in togglable:
        campo = campo_cfg['saida']
        ativo = bool(request.POST.get(f'campo_{campo}'))
        set_field_active(modelo, campo, ativo)

    messages.success(request, f"Colunas do resultado da análise atualizadas para \"{base_cfg['nome_base']}\".")
    return redirect('control_panel:bases_dados')


@require_POST
def base_excluir_view(request, modelo):
    base_cfg = _get_base_cfg(modelo)
    model_cls = LAYER_REGISTRY[modelo]['model']

    reset_db(model_cls)

    file_mgmt = utils.get_file_management()
    if file_mgmt and getattr(file_mgmt, base_cfg['arquivo_upload']):
        setattr(file_mgmt, base_cfg['arquivo_upload'], None)
        file_mgmt.save()

    messages.success(
        request,
        f"\"{base_cfg['nome_base']}\" excluída: arquivo removido e todos os registros apagados da tabela."
    )
    return redirect('control_panel:bases_dados')
