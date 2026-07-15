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


# Classifica cada base em um nível de risco, para permitir destacar
# visualmente (cor/borda) o que exige atenção imediata (embargos,
# desmatamento) do que é apenas cadastral/informativo.
_BASE_SEVERITY = (
    ("Embargos", "critical"),
    ("Embargoes", "critical"),
    ("Prodes", "critical"),
    ("Deforesta", "critical"),
    ("Mapbiomas", "critical"),
    ("APAs", "warning"),
    ("Indígenas", "warning"),
    ("Indigenas", "warning"),
    ("Quilombolas", "warning"),
    ("Unidades de Conservação", "warning"),
    ("Veredas", "warning"),
    ("IPUCA", "warning"),
    ("Assentamentos", "warning"),
)


@register.filter
def base_severity(nome_base):
    """Classifica uma base em 'critical', 'warning' ou 'info' conforme o risco que representa."""
    nome_base = nome_base or ""
    for chave, nivel in _BASE_SEVERITY:
        if chave in nome_base:
            return nivel
    return "info"


@register.filter
def pct_of_property(area, total_area):
    """Porcentagem que `area` (ha) representa de `total_area` (ha), ou None se não for calculável."""
    try:
        area = float(area or 0)
        total_area = float(total_area or 0)
    except (TypeError, ValueError):
        return None
    if total_area <= 0:
        return None
    return round((area / total_area) * 100, 1)


@register.filter
def bases_overview(bases):
    """Resume a lista de bases consultadas: quantas têm sobreposição e quantas são críticas/de atenção."""
    bases = bases or []
    com_sobreposicao = [b for b in bases if b.get("areas_encontradas")]
    sem_sobreposicao = [b for b in bases if not b.get("areas_encontradas")]
    criticas = sum(1 for b in com_sobreposicao if base_severity(b.get("nome_base")) == "critical")
    atencao = sum(1 for b in com_sobreposicao if base_severity(b.get("nome_base")) == "warning")
    return {
        "total": len(bases),
        "com_sobreposicao": len(com_sobreposicao),
        "sem_sobreposicao": len(sem_sobreposicao),
        "criticas": criticas,
        "atencao": atencao,
    }
