"""Andamento de uma análise em curso, para a tela do mapa 3D mostrar o que o
servidor está fazendo (ver `static/analysis/js/bases_3d.js`).

O formulário continua sendo um POST comum, que só responde quando a análise
termina. Junto com ele o navegador manda um `job_id` gerado na hora e, enquanto
espera a resposta, consulta `AnalysisProgressView` com esse id: a página sai
mostrando cada base consultada e os recortes encontrados no mapa. O estado fica
no cache (Redis em produção, compartilhado pelos workers do uWSGI), com a chave
presa ao usuário para ninguém ler o andamento de outro.

O botão "Cancelar" grava uma marca no cache; o pipeline confere essa marca
antes de cada base e para com `AnalysisCancelled`.
"""
import json
import re

from django.core.cache import cache

from analysis.services.analyze_coordinates.overlap.final_result_builder import FinalResultBuilder
from analysis.services.view_services.report_service import ALERTA, ATENCAO, MAPA_CORES, base_guide

JOB_ID_RE = re.compile(r'^[0-9a-f]{16,64}$')
TTL_SECONDS = 15 * 60

# O mapa só recebe o que acende o semáforo do relatório (embargo, PRODES,
# terra indígena...): APP, reserva legal, município etc. cobrem o imóvel
# inteiro e só poluiriam a animação.
DRAWN_LEVELS = (ALERTA, ATENCAO)
MAX_FEATURES = 60          # recortes mandados para o mapa, no total
SIMPLIFY_DEG = 0.00005     # ~5 m: o recorte é só ilustrativo
TARGET_SIMPLIFY_DEG = 0.00002


class AnalysisCancelled(Exception):
    """O usuário cancelou a análise pela tela."""


def _key(user_id, job_id):
    return f'analysis-progress:{user_id}:{job_id}'


def read_progress(user, job_id):
    if not JOB_ID_RE.match(job_id or ''):
        return None
    return cache.get(_key(user.pk, job_id))


def cancel_progress(user, job_id):
    if JOB_ID_RE.match(job_id or ''):
        cache.set(_key(user.pk, job_id) + ':cancel', True, TTL_SECONDS)


def _geojson(geom, tolerance):
    try:
        simple = geom.simplify(tolerance, preserve_topology=True)
        return json.loads(simple.json) if not simple.empty else None
    except Exception:
        return None


class AnalysisProgress:
    """Relata o andamento de uma análise. Sem `job_id` válido (outras telas,
    cruzamento em lote) todos os métodos viram no-op."""

    def __init__(self, user_id=None, job_id=None):
        self.key = _key(user_id, job_id) if user_id and JOB_ID_RE.match(job_id or '') else None
        self.state = {'stage': '', 'total': 0, 'done': 0, 'current': '', 'bases': [], 'features': []}
        self._names = FinalResultBuilder()._base_name

    @classmethod
    def from_request(cls, request):
        return cls(request.user.pk, request.POST.get('job_id', '').strip().lower())

    def __bool__(self):
        return self.key is not None

    def _save(self):
        if self.key:
            cache.set(self.key, self.state, TTL_SECONDS)

    def check_cancelled(self):
        if self.key and cache.get(self.key + ':cancel'):
            raise AnalysisCancelled()

    def stage(self, text, **extra):
        """Etapa fora do cruzamento (ler o PDF, montar o relatório...).
        `extra` vai junto para a tela, ex.: `car=` quando o PDF revela o CAR."""
        self.check_cancelled()
        self.state['stage'] = text
        self.state.update(extra)
        self._save()

    def target(self, geom):
        """Perímetro analisado: a tela usa quando não conseguiu localizar a
        área sozinha (PDF, shapefile sem .prj)."""
        if geom is not None and 'target' not in self.state:
            gj = _geojson(geom, TARGET_SIMPLIFY_DEG)
            if gj:
                self.state['target'] = gj
                self._save()

    def layers(self, layers):
        self.state['total'] = len(layers)
        self.state['bases'] = []
        for layer in layers:
            guide = base_guide(self._names(layer))
            self.state['bases'].append({
                'modelo': layer.__name__,
                'nome': guide['titulo'],
                'nivel': guide['nivel'],
                'status': 'pending',
                'count': 0,
                'area_ha': 0,
            })
        self._save()

    def _base(self, layer):
        for base in self.state['bases']:
            if base['modelo'] == layer.__name__:
                return base
        return None

    def layer_started(self, layer):
        self.check_cancelled()
        base = self._base(layer)
        if base:
            base['status'] = 'running'
            self.state['current'] = base['nome']
            self.state['stage'] = 'Consultando as bases'
        self._save()

    def layer_done(self, layer, rows):
        base = self._base(layer)
        if not base:
            return
        base['status'] = 'done'
        base['count'] = len(rows)
        base['area_ha'] = sum(r.get('intersection_area_ha') or 0 for r in rows)
        self.state['done'] = sum(1 for b in self.state['bases'] if b['status'] == 'done')
        if base['nivel'] in DRAWN_LEVELS:
            features = self.state['features']
            for row in rows:
                if len(features) >= MAX_FEATURES:
                    break
                gj = _geojson(row.get('intersection_geom'), SIMPLIFY_DEG) if row.get('intersection_geom') else None
                if gj:
                    features.append({'geometry': gj, 'color': MAPA_CORES[base['nivel']], 'base': base['nome']})
        self._save()

    def finish(self):
        self.state['stage'] = 'Abrindo o resultado'
        self.state['current'] = ''
        self.state['finished'] = True
        self._save()
