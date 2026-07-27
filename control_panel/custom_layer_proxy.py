"""
Ponte entre `CustomLayer` (base de dados criada pelo usuário no painel) e o
pipeline de análise de sobreposição (`analysis...overlap`), que foi escrito
para trabalhar com uma classe de Model Django por camada (`layer.__name__`,
`layer.objects.filter(...)`, etc.).

Em vez de criar um Model de verdade por base customizada — o que exigiria uma
migração de banco a cada nova base, inviabilizando "criar pela tela" — cada
`CustomLayer` ativa vira uma classe "proxy" mínima cujo `.objects` é só um
QuerySet de `CustomLayerFeature` já filtrado por `layer_id`. Um QuerySet
suporta os mesmos métodos que o pipeline usa (`.filter()`, `.exclude()`,
`.annotate()`, `.get()`, `.count()`), então `pipeline.py` e
`overlap_service.py` funcionam sem nenhuma alteração.
"""

from .models import CustomLayer, CustomLayerFeature


def build_active_layer_proxies():
    """[(proxy_class, custom_layer), ...] para cada CustomLayer com ativo=True."""
    proxies = []
    for custom_layer in CustomLayer.objects.filter(ativo=True):
        queryset = CustomLayerFeature.objects.filter(layer_id=custom_layer.id)
        proxy = type(custom_layer.proxy_name, (), {"objects": queryset})
        proxies.append((proxy, custom_layer))
    return proxies
