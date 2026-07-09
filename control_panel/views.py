from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import utils

CHART_WIDTH = 640
CHART_HEIGHT = 200
CHART_PADDING = 30


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
            'x': round(x, 1),
            'y': round(y, 1),
            'label_y': CHART_HEIGHT - 8,
            'label': snapshot.captured_at.strftime('%d/%m'),
            'percent': round(percent, 1),
        })

    polyline = ' '.join(f"{p['x']},{p['y']}" for p in points)

    def y_for_percent(percent):
        return round(CHART_PADDING + (100 - percent) / 100 * (CHART_HEIGHT - 2 * CHART_PADDING), 1)

    return {
        'width': CHART_WIDTH,
        'height': CHART_HEIGHT,
        'points': points,
        'polyline': polyline,
        'warning_y': y_for_percent(70),
        'critical_y': y_for_percent(90),
    }


def _storage_context(snapshot):
    percent = (snapshot.disk_used_bytes / snapshot.disk_total_bytes) * 100
    status_code, status_label = utils.get_storage_status(percent)

    return {
        'database_size': utils.format_bytes(snapshot.database_size_bytes),
        'disk_used': utils.format_bytes(snapshot.disk_used_bytes),
        'disk_total': utils.format_bytes(snapshot.disk_total_bytes),
        'percent': round(percent, 1),
        'status_code': status_code,
        'status_label': status_label,
        'last_updated': snapshot.captured_at,
        'chart': _build_chart(utils.get_last_7_days_snapshots()),
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
    return render(request, 'control_panel/usuarios.html', {'active_nav': 'usuarios'})
