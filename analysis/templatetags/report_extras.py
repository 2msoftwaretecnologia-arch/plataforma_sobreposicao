from django import template
from django.utils.formats import number_format

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
    ("Hidrografia", "💧"),
    ("APP Declarada", "🏞️"),
    ("Vegetação Nativa", "🌲"),
    ("Reserva Legal", "🍃"),
    ("Área Consolidada", "🚜"),
    ("Uso Restrito", "⛰️"),
    ("Pousio", "🌾"),
    ("Servidão", "⚡"),
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
    ("Hidrografia", "warning"),
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


@register.filter
def ha(value):
    """Área em hectares no formato brasileiro, com 2 casas (ex.: '1.234,57 ha')."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    if 0 < value < 0.01:
        return "menos de 0,01 ha"
    return f"{number_format(value, 2, use_l10n=True, force_grouping=True)} ha"


# Alqueire goiano, a medida usada no Tocantins.
_HA_POR_ALQUEIRE = 4.84


@register.filter
def alqueires(value):
    """Converte hectares para alqueires goianos (ex.: '22,2 alqueires')."""
    try:
        value = float(value) / _HA_POR_ALQUEIRE
    except (TypeError, ValueError):
        return ""
    return f"{number_format(value, 1, use_l10n=True, force_grouping=True)} alqueires"


@register.filter
def pct(value):
    """Porcentagem no formato brasileiro, com 1 casa (ex.: '35,2%')."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return ""
    if 0 < value < 0.1:
        return "menos de 0,1%"
    casas = 0 if round(value, 1).is_integer() else 1
    return f"{number_format(value, casas, use_l10n=True)}%"


_ZONING_MEANINGS = (
    ("ZDI", "Desenvolvimento intensivo: indicada para produção em larga escala, com restrições ambientais moderadas."),
    ("ZDE", "Desenvolvimento extensivo: indicada para pecuária, silvicultura ou agricultura de baixo impacto."),
    ("ZCE", "Conservação ecológica: prioriza a natureza; atividades humanas muito restritas."),
    ("ZAU", "Agropecuária e uso sustentável."),
    ("ZPA", "Proteção ambiental, semelhante a uma APA."),
    ("ZRE", "Recuperação ecológica: áreas degradadas que devem ser recuperadas."),
    ("ZMC", "Mineração, com licenciamento específico."),
    ("ZIT", "Interesse turístico: recreação e ecoturismo."),
    ("ZEUS", "Expansão urbana sustentável."),
    ("ZER", "Expansão restrita, com limitações legais."),
    ("ZR", "Zona rural, com uso agropecuário variado."),
    ("ZU", "Zona urbana."),
    ("ZP", "Preservação permanente."),
)


@register.filter
def zoning_meaning(sigla):
    """Explicação em linguagem simples para a sigla de zoneamento."""
    sigla = (sigla or "").strip().upper()
    if not sigla:
        return "-"
    for chave, texto in _ZONING_MEANINGS:
        if sigla == chave or sigla.startswith(chave + "-"):
            return texto
    return "Zona definida pelo zoneamento do Estado."
