"""
Serviço de leitura/escrita do estado de LayerFieldToggle — quais colunas de
cada camada aparecem no resultado da análise de sobreposição.
"""

from .models import LayerFieldToggle


def get_disabled_fields_map():
    """{modelo: {campo, ...}} apenas dos campos que o usuário desligou.

    Ausência de registro para um campo == campo ligado (padrão), então só
    precisamos saber quais estão explicitamente desativados.
    """
    disabled = {}
    for modelo, campo in LayerFieldToggle.objects.filter(ativo=False).values_list('modelo', 'campo'):
        disabled.setdefault(modelo, set()).add(campo)
    return disabled


def get_active_map_for_layer(modelo, campos_saida):
    """{campo: bool} de ligado/desligado para os campos togglable de uma
    camada, para desenhar os checkboxes no painel."""
    desligados = set(
        LayerFieldToggle.objects
        .filter(modelo=modelo, campo__in=campos_saida, ativo=False)
        .values_list('campo', flat=True)
    )
    return {campo: campo not in desligados for campo in campos_saida}


def set_field_active(modelo, campo, ativo):
    LayerFieldToggle.objects.update_or_create(
        modelo=modelo, campo=campo, defaults={'ativo': ativo}
    )
