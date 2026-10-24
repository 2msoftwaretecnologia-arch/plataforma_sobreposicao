"""Limites das análises pedidas pelo assistente.

Cada análise consulta todas as bases no banco do site; um assistente em loop
(ou vários usuários ao mesmo tempo) travaria a plataforma para todos. Por
isso há um teto de análises por minuto e por hora para cada usuário (no
cache, compartilhado entre processos) e de análises rodando ao mesmo tempo,
por usuário e no total (no processo, que é um só no serviço `mcp`).
Análises reaproveitadas do histórico não contam.
"""
import threading
import time
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache

_lock = threading.Lock()
_running = {}


class LimitExceeded(Exception):
    """Mensagem para o usuário: vira o erro da ferramenta."""


def _count(user_id, window, size):
    key = f'mcp-limite:{user_id}:{window}:{int(time.time() // size)}'
    cache.add(key, 0, size * 2)
    try:
        return cache.incr(key)
    except ValueError:
        # A chave expirou entre o `add` e o `incr`.
        cache.set(key, 1, size * 2)
        return 1


def check_rate(user_id):
    per_minute = settings.MCP_ANALYSES_PER_MINUTE
    per_hour = settings.MCP_ANALYSES_PER_HOUR
    if per_minute and _count(user_id, 'm', 60) > per_minute:
        raise LimitExceeded(
            f'Limite de {per_minute} análises por minuto atingido. Espere um minuto, ou use uma análise que já '
            'está no histórico (listar_analises).')
    if per_hour and _count(user_id, 'h', 3600) > per_hour:
        raise LimitExceeded(
            f'Limite de {per_hour} análises por hora atingido. Para muitas áreas de uma vez, use o cruzamento em '
            'lote da plataforma.')


@contextmanager
def analysis_slot(user_id):
    """Reserva uma vaga para rodar uma análise agora (ou recusa com `LimitExceeded`)."""
    check_rate(user_id)
    with _lock:
        mine = _running.get(user_id, 0)
        total = sum(_running.values())
        if mine >= settings.MCP_MAX_CONCURRENT_PER_USER:
            raise LimitExceeded(
                f'Você já tem {mine} análise(s) em andamento. Espere terminar antes de pedir outra.')
        if total >= settings.MCP_MAX_CONCURRENT_TOTAL:
            raise LimitExceeded('A plataforma está processando muitas análises agora. Tente de novo em um minuto.')
        _running[user_id] = mine + 1
    try:
        yield
    finally:
        with _lock:
            left = _running.get(user_id, 1) - 1
            if left > 0:
                _running[user_id] = left
            else:
                _running.pop(user_id, None)
