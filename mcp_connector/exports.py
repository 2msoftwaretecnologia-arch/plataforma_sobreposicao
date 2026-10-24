"""Arquivos de uma análise entregues pelo conector: KML/SHP e imagem do mapa.

O assistente não consegue repassar arquivos binários para a conversa, então
cada arquivo sai por um link assinado (`file_url`) que vale por
`MCP_FILE_LINK_MAX_AGE` e é gerado na hora em que é aberto, com as bases
liberadas para o dono do link naquele momento.
"""
import re
from xml.sax.saxutils import escape

import pandas as pd
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.text import slugify
from shapely import wkt as shapely_wkt

from analysis.models import SearchHistory
from analysis.services.view_services.base_export_service import (
    BaseExportError,
    base_geodataframe,
    export_filename,
    property_geodataframe,
    to_kml,
    to_shapefile_zip,
)
from analysis.services.view_services.cross_batch_service import _is_neutral
from analysis.services.view_services.report_service import ALERTA, ATENCAO, INFO, MAPA_CORES, base_guide
from analysis.validators import validate_car_number
from car_system.utils import get_sicar_record
from control_panel.access_service import require_layer
from control_panel.bases_config import BASES_CONFIG

from . import static_map
from .queries import QueryError, _num, _require_result, find_base, item_attributes, load_analysis

SIGNING_SALT = 'mcp_connector.arquivos'
FORMATS = {'kml', 'shp'}
# Bases que cobrem a área inteira e só descrevem o lugar: ficam fora do mapa
# "todas", senão escondem o resto.
CONTEXT_BASES = ('Zoneamento', 'Fitoecologias', 'Municípios', 'Municipios', 'Municpios')
BASE_COLORS = {b['nome_base']: b.get('cor') for b in BASES_CONFIG}
# Desenho do mapa: as mais graves por cima.
DRAW_ORDER = {INFO: 0, ATENCAO: 1, ALERTA: 2}


# ---------------------------------------------------------------------------
# Links assinados
# ---------------------------------------------------------------------------

def file_url(user, analise_id, kind, fmt, base='', fundo=''):
    payload = {'u': user.pk, 'a': analise_id, 'k': kind, 'f': fmt, 'b': base or '', 'm': fundo or ''}
    token = signing.dumps(payload, salt=SIGNING_SALT, compress=True)
    return settings.MCP_PUBLIC_BASE_URL + reverse('mcp_connector:arquivo', args=[token])


def read_token(token):
    """Conteúdo do link; `signing.SignatureExpired`/`BadSignature` se vencido ou adulterado."""
    return signing.loads(token, salt=SIGNING_SALT, max_age=settings.MCP_FILE_LINK_MAX_AGE)


def _real_items_with_geometry(base):
    return [i for i in base.get('areas_encontradas') or [] if not _is_neutral(i) and i.get('polygon_wkt')]


def download_links(user, analise_id):
    historico, data = load_analysis(user, analise_id)
    _require_result(historico, data)
    pk = historico.pk
    bases = [b for b in data['resultado']['resultados_por_base'] if _real_items_with_geometry(b)]
    hours = settings.MCP_FILE_LINK_MAX_AGE // 3600
    links = {
        'analise_id': pk,
        'validade': f'Os links valem {hours} horas e abrem sem login; não os compartilhe com quem não deve ver a análise.',
        'imovel': {fmt: file_url(user, pk, 'imovel', fmt) for fmt in ('kml', 'shp')},
        'mapa_png': file_url(user, pk, 'mapa', 'png'),
    }
    if bases:
        links['todas_as_sobreposicoes'] = {fmt: file_url(user, pk, 'sobreposicoes', fmt) for fmt in ('kml', 'shp')}
        links['por_base'] = [
            {
                'base': b['nome_base'],
                'itens': len(_real_items_with_geometry(b)),
                **{fmt: file_url(user, pk, 'base', fmt, base=b['nome_base']) for fmt in ('kml', 'shp')},
            }
            for b in bases
        ]
    else:
        links['observacao'] = 'Nenhuma base tem polígonos dentro da área; só o imóvel e o mapa podem ser baixados.'
    return links


# ---------------------------------------------------------------------------
# KML com pastas e cores por base
# ---------------------------------------------------------------------------

def _kml_color(color, alpha):
    """#RRGGBB → aabbggrr (ordem do KML)."""
    r, g, b = static_map._rgb(color)
    return f'{alpha:02x}{b:02x}{g:02x}{r:02x}'


def _kml_coords(coords):
    return ' '.join(f'{c[0]:.7f},{c[1]:.7f}' for c in coords)


def _kml_geometry(geom):
    kind = geom.geom_type
    if kind == 'Polygon':
        inner = ''.join(
            f'<innerBoundaryIs><LinearRing><coordinates>{_kml_coords(r.coords)}</coordinates></LinearRing></innerBoundaryIs>'
            for r in geom.interiors
        )
        return (f'<Polygon><outerBoundaryIs><LinearRing><coordinates>{_kml_coords(geom.exterior.coords)}'
                f'</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>')
    if kind == 'LineString':
        return f'<LineString><coordinates>{_kml_coords(geom.coords)}</coordinates></LineString>'
    if kind == 'Point':
        return f'<Point><coordinates>{_kml_coords(geom.coords)}</coordinates></Point>'
    if hasattr(geom, 'geoms'):
        parts = ''.join(_kml_geometry(g) for g in geom.geoms if not g.is_empty)
        return f'<MultiGeometry>{parts}</MultiGeometry>'
    return ''


def _kml_placemark(name, wkt, style, attributes):
    try:
        geom = shapely_wkt.loads(wkt)
    except Exception:
        return ''
    if geom.is_empty:
        return ''
    data = ''.join(
        f'<Data name="{escape(str(k), {chr(34): "&quot;"})}"><value>{escape(str(v))}</value></Data>'
        for k, v in attributes.items()
    )
    return (f'<Placemark><name>{escape(name)}</name><styleUrl>#{style}</styleUrl>'
            f'<ExtendedData>{data}</ExtendedData>{_kml_geometry(geom)}</Placemark>')


def base_color(nome_base, items=()):
    for item in items:
        if item.get('color'):
            return item['color']
    return BASE_COLORS.get(nome_base) or MAPA_CORES[base_guide(nome_base)['nivel']]


def overlaps_kml(data, title):
    """Um KML com o imóvel e uma pasta colorida por base (abre no Google Earth/QGIS)."""
    resultado = data['resultado']
    styles = [
        f'<Style id="imovel"><LineStyle><color>{_kml_color(static_map.PROPERTY_COLOR, 255)}</color><width>3</width>'
        '</LineStyle><PolyStyle><fill>0</fill></PolyStyle></Style>'
    ]
    folders = []
    if resultado.get('alvo_wkt'):
        car = data.get('car_input') or 'Imóvel analisado'
        folders.append('<Folder><name>Imóvel analisado</name>'
                       f"{_kml_placemark(car, resultado['alvo_wkt'], 'imovel', {'area_ha': _num(resultado.get('tamanho_area'))})}"
                       '</Folder>')
    for n, base in enumerate(resultado.get('resultados_por_base') or []):
        items = _real_items_with_geometry(base)
        if not items:
            continue
        nome = base.get('nome_base') or ''
        color = base_color(nome, items)
        styles.append(
            f'<Style id="base{n}"><LineStyle><color>{_kml_color(color, 255)}</color><width>2</width></LineStyle>'
            f'<PolyStyle><color>{_kml_color(color, 0x66)}</color></PolyStyle></Style>'
        )
        placemarks = ''.join(
            _kml_placemark(item.get('item_info') or nome, item['polygon_wkt'], f'base{n}',
                           {'base': nome, 'area_ha': _num(item.get('area')), **item_attributes(item)})
            for item in items
        )
        folders.append(f'<Folder><name>{escape(nome)} ({len(items)})</name>{placemarks}</Folder>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f'<name>{escape(title)}</name>{"".join(styles)}{"".join(folders)}</Document></kml>'
    ).encode('utf-8')


def overlaps_geodataframe(resultado):
    """Todas as bases num GeoDataFrame só, com a coluna `base`."""
    frames = []
    for base in resultado.get('resultados_por_base') or []:
        if not _real_items_with_geometry(base):
            continue
        clean = {**base, 'areas_encontradas': _real_items_with_geometry(base)}
        gdf = base_geodataframe(clean)
        gdf.insert(0, 'base', base.get('nome_base') or '')
        frames.append(gdf)
    if not frames:
        raise BaseExportError('Nenhuma base tem polígonos dentro da área para exportar.')
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------

def _ha(value):
    return f'{value or 0:,.2f} ha'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _short(text, size=55):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= size else text[:size - 1] + '…'


def map_layers(resultado, base=None):
    """Camadas do mapa, a descrição do que ele mostra e notas para a legenda.

    Sem `base`: as bases de alerta e atenção. `base="todas"`: tudo, menos as
    bases que só descrevem o lugar (zoneamento, vegetação, município). Com o
    nome de uma base: os itens dela, cada um com uma cor quando são poucos.
    Como no relatório impresso, uma base com um item só cobrindo a área
    inteira não é pintada (esconderia o resto): vira uma nota.
    """
    if base and base.strip().lower() != 'todas':
        found = find_base(resultado, base)
        nome = found.get('nome_base') or ''
        items = [i for i in found.get('areas_encontradas') or [] if not _is_neutral(i) and i.get('polygon_geojson')]
        if not items:
            raise QueryError(f'A base "{nome}" não tem polígonos dentro da área.')
        if len(items) <= len(static_map.ITEM_PALETTE):
            layers = [
                {'label': _short(i.get('item_info') or nome), 'color': static_map.ITEM_PALETTE[n],
                 'detail': _ha(_num(i.get('area'))), 'geometries': [i['polygon_geojson']]}
                for n, i in enumerate(items)
            ]
        else:
            total = sum(_num(i.get('area')) or 0 for i in items)
            layers = [{'label': _short(nome), 'color': base_color(nome, items),
                       'detail': f'{len(items)} itens · {_ha(total)}',
                       'geometries': [i['polygon_geojson'] for i in items]}]
        return layers, nome, []

    everything = bool(base)
    tamanho = _num(resultado.get('tamanho_area')) or 0
    selected, covering = [], []
    for found in resultado.get('resultados_por_base') or []:
        nome = found.get('nome_base') or ''
        nivel = base_guide(nome)['nivel']
        if everything and any(chave in nome for chave in CONTEXT_BASES):
            continue
        if not everything and nivel == INFO:
            continue
        items = [i for i in found.get('areas_encontradas') or [] if not _is_neutral(i) and i.get('polygon_geojson')]
        if len(items) == 1 and tamanho and (_num(items[0].get('area')) or 0) >= tamanho * 0.99:
            # Só o nome, sem os demais campos ("APA: APA Ilha do Bananal/Cantão | Domínios: ...").
            covering.append(f"{base_guide(nome)['titulo']} — {_short(str(items[0].get('item_info') or '').split(' | ')[0], 50)}")
        elif items:
            selected.append((nivel, nome, items))
    selected.sort(key=lambda s: DRAW_ORDER[s[0]])
    layers = [
        {'label': _short(base_guide(nome)['titulo']), 'color': base_color(nome, items),
         'detail': _ha(sum(_num(i.get('area')) or 0 for i in items)),
         'geometries': [i['polygon_geojson'] for i in items]}
        for _, nome, items in selected
    ]
    notes = [f"Cobrem toda a área (não pintadas): {'; '.join(covering)}."] if covering else []
    return layers, 'Todas as bases com sobreposição' if everything else 'Bases de alerta e atenção', notes


def render_analysis_map(historico, data, base=None, fundo='satelite'):
    resultado = data['resultado']
    layers, showing, notes = map_layers(resultado, base)
    car = data.get('car_input') or ''
    if historico.search_type == SearchHistory.SearchType.SIGEF:
        title = f'Parcela SIGEF {car}'
    elif car:
        try:
            title = f'CAR {validate_car_number(car)}'
        except ValidationError:
            title = car
    else:
        title = f'Análise nº {historico.pk}'
    place = '/'.join(p for p in (data.get('municipio'), data.get('uf')) if p)
    subtitle = ' · '.join(p for p in (
        place, _ha(_num(resultado.get('tamanho_area'))), showing,
        f'Análise nº {historico.pk} de {historico.created_at:%d/%m/%Y}',
    ) if p)
    try:
        png = static_map.render_map(resultado.get('alvo_geojson'), layers, title, subtitle, fundo, notes=notes)
    except static_map.MapRenderError as exc:
        raise QueryError(str(exc)) from None
    return png, layers, showing, notes


def analysis_map(user, analise_id, base=None, fundo='satelite'):
    """PNG do mapa e o resumo do que foi desenhado (para o texto da resposta)."""
    historico, data = load_analysis(user, analise_id)
    _require_result(historico, data)
    png, layers, showing, notes = render_analysis_map(historico, data, base, fundo)
    info = {
        'analise_id': historico.pk,
        'mostrando': showing,
        'camadas': [{'nome': layer['label'], 'cor': layer['color'], 'detalhe': layer['detail']} for layer in layers],
        'link_png': file_url(user, historico.pk, 'mapa', 'png', base=base or '', fundo=fundo),
    }
    if notes:
        info['notas'] = notes
    if not layers:
        info['observacao'] = 'Nada a pintar nessas bases: o mapa mostra só o contorno da área.'
    return png, info


# ---------------------------------------------------------------------------
# Arquivo pedido pelo link
# ---------------------------------------------------------------------------

def _car_status(data, user):
    status = (data.get('demonstrativo') or {}).get('registration_status') or ''
    car = data.get('car_input') or ''
    if not status and car and data.get('source_model') != 'Sigef':
        require_layer('SicarRecord', user)
        record = get_sicar_record(car_number__iexact=car).first()
        status = getattr(record, 'status', '') or ''
    return status


def build_file(user, payload):
    """(conteúdo, nome do arquivo, content type) do link `payload` (ver `file_url`)."""
    historico, data = load_analysis(user, payload['a'])
    _require_result(historico, data)
    kind, fmt, base = payload['k'], payload['f'], payload.get('b') or ''
    resultado = data['resultado']
    car = data.get('car_input') or ''

    if kind == 'mapa':
        png = render_analysis_map(historico, data, base or None, payload.get('m') or 'satelite')[0]
        suffix = slugify(base) if base else 'alertas'
        return png, f'mapa_{slugify(car) or historico.pk}_{suffix}.png', 'image/png'
    if fmt not in FORMATS:
        raise QueryError('Formato inválido.')

    try:
        if kind == 'imovel':
            gdf = property_geodataframe(resultado.get('alvo_wkt'), car, _car_status(data, user))
            name = f'propriedade_{slugify(car)}' if car else 'propriedade'
        elif kind == 'sobreposicoes':
            name = export_filename('sobreposicoes', car)
            if fmt == 'kml':
                return overlaps_kml(data, f'Sobreposições — {car or f"análise {historico.pk}"}'), \
                    f'{name}.kml', 'application/vnd.google-earth.kml+xml'
            gdf = overlaps_geodataframe(resultado)
        elif kind == 'base':
            found = find_base(resultado, base)
            gdf = base_geodataframe(found)
            name = export_filename(found['nome_base'], car)
        else:
            raise QueryError('Arquivo inválido.')
    except BaseExportError as exc:
        raise QueryError(str(exc)) from None

    if fmt == 'kml':
        return to_kml(gdf, name), f'{name}.kml', 'application/vnd.google-earth.kml+xml'
    return to_shapefile_zip(gdf, name), f'{name}.zip', 'application/zip'
