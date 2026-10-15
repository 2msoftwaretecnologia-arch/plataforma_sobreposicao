"""Autorização central de bases, inclusive para resultados salvos."""
from copy import deepcopy
from django.core.exceptions import PermissionDenied
from .models import LayerAccessPolicy
from .bases_config import BASES_CONFIG


def denied_layers(user=None):
    policies = LayerAccessPolicy.objects.filter(restrita=True).prefetch_related('grupos')
    if user and user.is_authenticated and user.is_active:
        if user.is_staff or user.is_superuser:
            return set()
        groups = set(user.groups.values_list('pk', flat=True))
    else:
        groups = set()
    return {p.modelo for p in policies if not groups.intersection(g.pk for g in p.grupos.all())}


def require_layer(modelo, user=None):
    if modelo in denied_layers(user):
        raise PermissionDenied('Você não tem acesso a esta base de dados.')


def filter_result(data, user=None, denied=None):
    """Reconstrói agregados para não revelar dados após revogação de acesso."""
    data = deepcopy(data)
    denied = denied_layers(user) if denied is None else denied
    source = data.get('source_model') or ('SicarRecord' if data.get('car_input') else None)
    if source in denied:
        raise PermissionDenied('Você não tem mais acesso à base de origem deste resultado.')
    names = {b['nome_base'] for b in BASES_CONFIG if b['modelo'] in denied}
    if 'MunicipalBoundaries' in denied:
        data['municipio'] = ''
    result = data.get('resultado') or {}
    bases = [b for b in result.get('resultados_por_base', []) if b.get('nome_base') not in names]
    if 'resultados_por_base' in result:
        result['resultados_por_base'] = bases
        result['areas_encontradas'] = [a for b in bases for a in b.get('areas_encontradas', [])]
        result['total_areas_com_sobreposicao'] = len(result['areas_encontradas'])
        result['poligonos_imoveis'] = [p for p in result.get('poligonos_imoveis', []) if p.get('fonte') not in names]
        result['resumo_bases'] = {k:v for k,v in result.get('resumo_bases', {}).items() if k not in names}
        if 'PhytoecologyArea' in denied:
            result['area_preservada_total'] = 0
        data['resultado'] = result
    return data


def filter_batch_item(item, user=None, denied=None):
    denied = denied_layers(user) if denied is None else denied
    if 'MunicipalBoundaries' in denied:
        item.municipio = ''
    names = {b['nome_base'] for b in BASES_CONFIG if b['modelo'] in denied}
    summary = deepcopy(item.summary or {})
    bases = [b for b in summary.get('bases', []) if b.get('nome') not in names]
    summary['bases'] = bases
    item.overlap_count = sum(b.get('count', 0) for b in bases)
    item.critical_count = sum(1 for b in bases if b.get('count') and b.get('severity') == 'critical')
    item.warning_count = sum(1 for b in bases if b.get('count') and b.get('severity') == 'warning')
    summary['total_areas_com_sobreposicao'] = item.overlap_count
    if 'Base de Dados de Fitoecologias' in names:
        summary['area_preservada_total'] = 0
    item.summary = summary
    return item
