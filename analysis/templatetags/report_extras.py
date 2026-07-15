from django import template

register = template.Library()

# Ordem importa: mantém correspondência com os mesmos trechos de nome usados
# em report_print.html para escolher a tabela de cada base.
_BASE_ICONS = (
    ("Sigef", "📐"),
    ("Zoneamento", "🗺️"),
    ("Municípios", "🏛️"),
    ("Municipios", "🏛️"),
    ("Municpios", "🏛️"),
    ("APAs", "🌿"),
    ("Indígenas", "🪶"),
    ("Indigenas", "🪶"),
    ("Quilombolas", "🏘️"),
    ("Assentamentos", "🏡"),
    ("Sicar", "📄"),
    ("CAR", "📄"),
    ("Fitoecologias", "🌳"),
    ("Veredas", "💧"),
    ("IPUCA", "🌱"),
    ("Unidades de Conservação", "🏞️"),
    ("SNIC", "🏭"),
    ("Deforestação", "🔥"),
    ("Mapbiomas", "🔥"),
    ("Embargos", "🚫"),
    ("Embargoes", "🚫"),
    ("Prodes", "📡"),
)


@register.filter
def base_icon(nome_base):
    """Retorna um emoji representativo para o nome da base de sobreposição."""
    nome_base = nome_base or ""
    for chave, icone in _BASE_ICONS:
        if chave in nome_base:
            return icone
    return "📌"
