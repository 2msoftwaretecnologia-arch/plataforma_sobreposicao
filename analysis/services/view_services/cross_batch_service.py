"""Cruzamento em lote: todos os CARs encontrados na tela de Localizações
cruzados com as demais bases, em segundo plano.

Cada CAR passa pelo mesmo motor da busca por número do CAR (`SearchForCar`),
mas do resultado só fica guardado um resumo por base (itens e áreas): o
resultado completo traz as geometrias e chega a vários MB por CAR. O relatório
completo com mapa de um CAR continua disponível sob demanda, pela busca por CAR.

Execução: pelo Celery quando o broker responde (produção); senão numa thread
do próprio processo web (ambiente local, onde não há broker). O progresso fica
no banco, então um lote interrompido é retomado de onde parou (`resume_if_stale`).
"""
import logging
import queue
import threading
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import F
from django.utils import timezone

from analysis.models import CrossBatch, CrossBatchItem
from analysis.services.analyze_coordinates.search_for_car import SearchForCar
from analysis.services.analyze_coordinates.search_for_sigef import SearchForSigef
from analysis.templatetags.report_extras import base_severity
from car_system.models import SicarRecord
from gov.models import Sigef

logger = logging.getLogger(__name__)

# CARs processados ao mesmo tempo. Cada um faz uma consulta espacial por base
# no mesmo Postgres usado pelo site, então não vale subir muito.
WORKERS = 3
# Itens guardados por base no resumo de cada CAR (o total sempre é guardado).
MAX_ITEMS_PER_BASE = 100
# Sem progresso por esse tempo com o lote "processando" = processo caiu. Com
# 3 CARs em paralelo o progresso anda a cada poucos segundos (o CAR mais
# demorado medido levou ~25 s), então 2 min sem nada já é parada.
STALE_AFTER = timedelta(minutes=2)
# Lote "na fila" há mais que isso: o Celery não pegou (broker sem worker).
QUEUE_TIMEOUT = timedelta(minutes=1)
# Tempo médio de um CAR, para a estimativa mostrada antes de começar.
SECONDS_PER_CAR = 5


def estimate_minutes(total_cars: int) -> int:
    return max(1, round(total_cars * SECONDS_PER_CAR / WORKERS / 60))


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_neutral(item: dict) -> bool:
    """As camadas de UCs e APAs cobrem o estado inteiro: o que fica fora de
    qualquer unidade vem como um polígono "sem unidade". Tocar nele não é
    restrição, então não conta como alerta no lote."""
    return 'sem unidade' in str(item.get('item_info', '')).lower()


def summarize_result(result: dict) -> dict:
    """Resumo compacto do resultado do `SearchAll` para guardar no lote.

    Por base: `count`/`total_area` contam só as sobreposições reais (sem os
    itens neutros); os itens neutros ficam na lista marcados com `neutral`.
    """
    bases = []
    for base in result.get('resultados_por_base') or []:
        name = base.get('nome_base', '')
        areas = base.get('areas_encontradas') or []
        real = [item for item in areas if not _is_neutral(item)]
        items = [
            {
                'info': item.get('item_info', ''),
                'area': _to_float(item.get('area')),
                'sigla': item.get('sigla') or '',
                'zona': item.get('zona') or '',
                'neutral': _is_neutral(item),
            }
            for item in areas[:MAX_ITEMS_PER_BASE]
        ]
        bases.append({
            'nome': name,
            'severity': base_severity(name),
            'count': len(real),
            'total_area': round(sum(_to_float(item.get('area')) or 0 for item in real), 4),
            'neutral_count': len(areas) - len(real),
            'items': items,
            'truncated': max(0, len(areas) - MAX_ITEMS_PER_BASE),
        })
    return {
        'tamanho_area': _to_float(result.get('tamanho_area')),
        'area_preservada_total': _to_float(result.get('area_preservada_total')),
        'total_areas_com_sobreposicao': result.get('total_areas_com_sobreposicao') or 0,
        'tempo': result.get('tempo_execucao_formatado', ''),
        'bases': bases,
    }


def create_batch(user, title: str, cars: list, kind: str = CrossBatch.Kind.CAR) -> CrossBatch:
    """Cria o lote a partir dos CARs (ou parcelas do SIGEF) da tela de Localizações.

    `cars`: [{car, mun, pontos: [{i, n, lat, lon}]}] — `car` é o número do CAR
    ou o código da parcela. Só entram identificadores que existem na base;
    situação e área vêm do banco, não do navegador.
    """
    by_number = {}
    for car in cars:
        number = str(car.get('car') or '').strip().upper()
        if number and number not in by_number:
            by_number[number] = car

    if kind == CrossBatch.Kind.SIGEF:
        rows = [
            (r.installment_code, r.status, r.area_ha,
             {'name': (r.name or '').strip(' -'), 'property_code': r.property_code or ''})
            for r in Sigef.objects.filter(installment_code__in=[n.lower() for n in by_number] + list(by_number))
            .only('installment_code', 'status', 'area_ha', 'name', 'property_code')
        ]
    else:
        kind = CrossBatch.Kind.CAR
        rows = [
            (r.car_number, r.status, r.area_ha, {})
            for r in SicarRecord.objects.filter(car_number__in=list(by_number)).only('car_number', 'status', 'area_ha')
        ]
    records = {}
    for number, status, area_ha, extra in rows:
        records.setdefault(number.upper(), (number, status, area_ha, extra))

    batch = CrossBatch.objects.create(user=user, title=title[:255], total=len(records), kind=kind)
    CrossBatchItem.objects.bulk_create([
        CrossBatchItem(
            batch=batch,
            car_number=number,
            municipio=str(by_number[key].get('mun') or '')[:150],
            car_status=status or '',
            area_ha=area_ha,
            points=_clean_points(by_number[key].get('pontos')),
            extra=extra,
        )
        for key, (number, status, area_ha, extra) in records.items()
    ])
    return batch


def _clean_points(points) -> list:
    cleaned = []
    for p in (points or [])[:2000]:
        try:
            cleaned.append({
                'i': int(p.get('i')),
                'n': str(p.get('n') or '')[:300],
                'lat': float(p.get('lat')),
                'lon': float(p.get('lon')),
            })
        except (TypeError, ValueError, AttributeError):
            continue
    return cleaned


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def start_batch(batch: CrossBatch) -> str:
    """Dispara o processamento. Devolve 'celery' ou 'thread'."""
    if _celery_available():
        from analysis.tasks import run_cross_batch_task
        try:
            run_cross_batch_task.apply_async(args=[batch.pk], retry=False)
            return 'celery'
        except Exception:
            logger.warning('Falha ao enfileirar o lote %s no Celery; rodando em thread.', batch.pk, exc_info=True)
    _start_thread(batch.pk)
    return 'thread'


def resume_if_stale(batch: CrossBatch) -> bool:
    """Retoma um lote parado: na fila sem ninguém pegar, ou processando sem
    progresso há muito tempo. Devolve True se retomou."""
    now = timezone.now()
    stale = (
        (batch.status == CrossBatch.Status.PENDING and now - batch.created_at > QUEUE_TIMEOUT)
        or (batch.status == CrossBatch.Status.RUNNING
            and now - (batch.heartbeat_at or batch.started_at or batch.created_at) > STALE_AFTER)
    )
    if not stale:
        return False
    # Marca o heartbeat antes de disparar para duas requisições seguidas não
    # retomarem o mesmo lote duas vezes.
    updated = CrossBatch.objects.filter(pk=batch.pk, status=batch.status, heartbeat_at=batch.heartbeat_at).update(
        heartbeat_at=now,
    )
    if updated:
        _start_thread(batch.pk)
    return bool(updated)


def _celery_available() -> bool:
    try:
        from kombu import Connection
        with Connection(settings.CELERY_BROKER_URL, connect_timeout=2) as conn:
            conn.ensure_connection(max_retries=1)
        return True
    except Exception:
        return False


def _start_thread(batch_id: int):
    threading.Thread(target=run_batch, args=(batch_id,), daemon=True, name=f'lote-cruzamento-{batch_id}').start()


def run_batch(batch_id: int):
    """Processa os CARs pendentes do lote (chamado pelo Celery ou pela thread)."""
    try:
        batch = CrossBatch.objects.get(pk=batch_id)
        if batch.status == CrossBatch.Status.DONE:
            return
        now = timezone.now()
        CrossBatch.objects.filter(pk=batch_id).update(
            status=CrossBatch.Status.RUNNING, started_at=batch.started_at or now, heartbeat_at=now, error='',
            # Ao retomar um lote interrompido, parte do que já está salvo.
            processed=batch.items.exclude(status=CrossBatchItem.Status.PENDING).count(),
        )
        pending = list(batch.items.filter(status=CrossBatchItem.Status.PENDING).values_list('pk', flat=True))
        _run_in_daemon_threads(pending)

        # Contagem final pelo banco (o `processed` incremental pode ter
        # contado itens de uma execução anterior interrompida).
        processed = batch.items.exclude(status=CrossBatchItem.Status.PENDING).count()
        if processed < batch.total:
            # Sobrou item pendente por erro inesperado: deixa "processando"
            # para `resume_if_stale` refazer só os que faltam.
            CrossBatch.objects.filter(pk=batch_id).update(processed=processed)
            return
        CrossBatch.objects.filter(pk=batch_id).update(
            status=CrossBatch.Status.DONE, processed=processed,
            finished_at=timezone.now(), heartbeat_at=timezone.now(),
        )
    except Exception as exc:
        logger.exception('Falha no lote de cruzamento %s.', batch_id)
        CrossBatch.objects.filter(pk=batch_id).update(status=CrossBatch.Status.ERROR, error=str(exc)[:2000])
    finally:
        connection.close()


def _run_in_daemon_threads(item_ids: list):
    """Processa os itens com `WORKERS` threads daemon.

    Não usa `ThreadPoolExecutor`: as threads dele não são daemon e o Python
    espera por elas ao sair — no `runserver` isso travava o recarregamento
    automático e o Ctrl+C até o lote inteiro terminar (o servidor seguia
    atendendo com o código antigo). Com daemon, se o processo sair o lote só
    para e é retomado depois (`resume_if_stale`)."""
    fila = queue.Queue()
    for item_id in item_ids:
        fila.put(item_id)

    def worker():
        while True:
            try:
                item_id = fila.get_nowait()
            except queue.Empty:
                return
            try:
                _process_item_safely(item_id)
            except Exception:
                # Erro fora do cruzamento (ex.: banco caiu): o item fica
                # pendente e é refeito quando o lote for retomado.
                logger.exception('Falha inesperada no item %s do lote de cruzamento.', item_id)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(WORKERS, len(item_ids)) or 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _process_item_safely(item_id: int):
    close_old_connections()
    try:
        _process_item(item_id)
    finally:
        # Cada thread do pool tem a própria conexão com o banco.
        connection.close()


def _process_item(item_id: int):
    item = CrossBatchItem.objects.select_related('batch').get(pk=item_id)
    if item.status != CrossBatchItem.Status.PENDING:
        return
    try:
        if item.batch.kind == CrossBatch.Kind.SIGEF:
            result = SearchForSigef().execute(item.car_number, save_debug_files=False)
            if not result:
                raise ValueError('Parcela não encontrada ou sem geometria válida no SIGEF.')
        else:
            result = SearchForCar().execute(item.car_number, save_debug_files=False)
            if not result:
                raise ValueError('CAR não encontrado ou sem geometria válida no SICAR.')
        summary = summarize_result(result)
        with_overlap = [b for b in summary['bases'] if b['count']]
        item.summary = summary
        item.overlap_count = summary['total_areas_com_sobreposicao']
        item.critical_count = sum(1 for b in with_overlap if b['severity'] == 'critical')
        item.warning_count = sum(1 for b in with_overlap if b['severity'] == 'warning')
        item.status = CrossBatchItem.Status.DONE
        item.error = ''
    except Exception as exc:
        logger.warning('Falha ao cruzar o CAR %s (lote %s).', item.car_number, item.batch_id, exc_info=True)
        item.status = CrossBatchItem.Status.ERROR
        item.error = str(exc)[:2000]
    item.finished_at = timezone.now()
    item.save(update_fields=[
        'summary', 'overlap_count', 'critical_count', 'warning_count', 'status', 'error', 'finished_at',
    ])
    CrossBatch.objects.filter(pk=item.batch_id).update(processed=F('processed') + 1, heartbeat_at=timezone.now())
