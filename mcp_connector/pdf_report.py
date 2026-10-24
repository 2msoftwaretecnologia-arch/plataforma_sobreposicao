"""Relatório da análise em PDF, entregue pelo conector por link assinado.

Mesmo conteúdo de `relatorio_analise` (o semáforo, as bases com ocorrência,
Reserva Legal, uso do solo e a data de cada base), com o mapa da análise e a
fonte da imagem. Montado com o ReportLab, sem navegador: o relatório para
imprimir da tela desenha os mapas com JavaScript.
"""
import io
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LOCAL_TZ = ZoneInfo('America/Sao_Paulo')
GREEN = colors.HexColor('#16241e')
STATUS = {
    'alerta': ('#dc2626', 'Alerta'),
    'atencao': ('#f59e0b', 'Atenção'),
    'ok': ('#16a34a', 'OK'),
    'info': ('#3b82f6', 'Informativo'),
    'sem_dado': ('#9ca3af', 'Sem dado'),
}
VEREDITO_COLORS = {
    'Há pontos de alerta': '#dc2626',
    'Há pontos para conferir': '#f59e0b',
    'Nenhum problema encontrado': '#16a34a',
}
MARGIN = 1.6 * cm
WIDTH = A4[0] - 2 * MARGIN

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle('titulo', parent=_styles['Title'], fontSize=17, leading=21, textColor=GREEN, spaceAfter=2)
SUBTITLE = ParagraphStyle('subtitulo', parent=_styles['Normal'], fontSize=9.5, textColor=colors.HexColor('#555555'),
                          alignment=TA_CENTER, spaceAfter=10)
H2 = ParagraphStyle('h2', parent=_styles['Heading2'], fontSize=12.5, leading=15, textColor=GREEN,
                    spaceBefore=12, spaceAfter=5)
BODY = ParagraphStyle('corpo', parent=_styles['Normal'], fontSize=9, leading=11.5)
SMALL = ParagraphStyle('pequeno', parent=BODY, fontSize=7.8, leading=9.8, textColor=colors.HexColor('#444444'))
CELL = ParagraphStyle('celula', parent=BODY, fontSize=8.3, leading=10.3)
CELL_BOLD = ParagraphStyle('celula_negrito', parent=CELL, fontName='Helvetica-Bold')


def _text(value):
    """Texto seguro para o Paragraph: só caracteres da fonte padrão e XML escapado."""
    text = '' if value is None else str(value)
    return escape(text.encode('cp1252', 'replace').decode('cp1252'))


def _p(value, style=CELL):
    return Paragraph(_text(value), style)


def _ha(value, digits=2):
    if value is None:
        return '—'
    return f'{value:,.{digits}f} ha'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _pct(value):
    return '—' if value is None else f'{value:.1f}%'.replace('.', ',')


def _table(rows, widths, header=True, zebra=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d4d4d4')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8efe9'))]
    if zebra:
        style += [('ROWBACKGROUNDS', (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor('#fafafa')])]
    table.setStyle(TableStyle(style))
    return table


def _status_cell(status):
    color, label = STATUS.get(status, ('#9ca3af', status or '—'))
    return Paragraph(f'<font color="{color}"><b>{_text(label)}</b></font>', CELL)


def _identification(report):
    loc = report.get('localizacao') or {}
    place = '/'.join(p for p in (report.get('municipio'), report.get('uf')) if p)
    rows = [
        ('CAR / identificação', report.get('car')),
        ('Imóvel', report.get('nome_imovel')),
        ('Proprietários', ', '.join(_owner(p) for p in report.get('proprietarios') or []) or None),
        ('Município', place or None),
        ('Área analisada', _ha(report.get('area_imovel_ha'), 4)),
        ('Coordenada central', f"{loc['latitude']:.6f}, {loc['longitude']:.6f}" if loc else None),
        ('Análise', f"nº {report['analise_id']} de {report['data']}"),
    ]
    data = [[_p(label, CELL_BOLD), _p(value or '—')] for label, value in rows]
    return _table(data, [4.2 * cm, WIDTH - 4.2 * cm], header=False, zebra=False)


def _owner(owner):
    if isinstance(owner, dict):
        return ' — '.join(str(v) for v in (owner.get('nome'), owner.get('cpf_cnpj')) if v)
    return str(owner)


def _verdict(report):
    color = VEREDITO_COLORS.get(report['veredito'], '#16241e')
    text = (f'<font color="white"><b>{_text(report["veredito"])}</b> &nbsp; '
            f'{report["alertas"]} alerta(s) · {report["pontos_de_atencao"]} ponto(s) de atenção</font>')
    table = Table([[Paragraph(text, ParagraphStyle('v', parent=BODY, fontSize=11, leading=14))]], colWidths=[WIDTH])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(color)),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table


def _map(map_png, fonte, map_error):
    if not map_png:
        return [_p(f'Mapa indisponível: {map_error or "sem imagem"}.', SMALL)]
    image = Image(io.BytesIO(map_png), width=WIDTH, height=WIDTH * 900 / 1400)
    parts = [image]
    if fonte and fonte.get('descricao'):
        parts.append(Spacer(1, 3))
        parts.append(_p(f"Fonte da imagem: {fonte['descricao']}", SMALL))
    return [KeepTogether(parts)]


def _checklist(report):
    rows = [[_p('Pergunta', CELL_BOLD), _p('Situação', CELL_BOLD), _p('Resposta e explicação', CELL_BOLD)]]
    for check in report.get('perguntas') or []:
        rows.append([
            _p(check.get('pergunta')),
            _status_cell(check.get('status')),
            Paragraph(f"<b>{_text(check.get('resposta'))}</b><br/>{_text(check.get('explicacao'))}", CELL),
        ])
    return _table(rows, [5.2 * cm, 2.4 * cm, WIDTH - 7.6 * cm])


def _bases(report):
    rows = [[_p(h, CELL_BOLD) for h in ('Base', 'Nível', 'Área', '% do imóvel', 'O que significa')]]
    for base in report.get('bases_com_ocorrencia') or []:
        itens = '; '.join(f"{i['descricao']} ({_ha(i['area_ha'])})" for i in (base.get('itens') or [])[:6])
        rows.append([
            _p(base.get('titulo') or base.get('base')),
            _status_cell(base.get('nivel')),
            _p(_ha(base.get('area_ha'))),
            _p(_pct(base.get('percentual_do_imovel'))),
            Paragraph(f"{_text(base.get('o_que_significa'))}"
                      + (f"<br/><font size=7 color='#555555'>{_text(itens)}</font>" if itens else ''), CELL),
        ])
    return _table(rows, [3.6 * cm, 2.2 * cm, 2.3 * cm, 1.9 * cm, WIDTH - 10 * cm])


def _land_use(report):
    uso = report.get('uso_do_solo_mapbiomas') or {}
    if uso.get('erro'):
        return [_p(f"Comparativo de uso do solo indisponível: {uso['erro']}", SMALL)]
    antes, depois = uso.get('ano_antes'), uso.get('ano_depois')
    parts = [_p(
        f"Vegetação nativa: {_ha(uso.get('vegetacao_nativa_antes_ha'))} em {antes} e "
        f"{_ha(uso.get('vegetacao_nativa_depois_ha'))} em {depois}. Retirada: "
        f"{_ha(uso.get('vegetacao_retirada_ha'))}; regenerada: {_ha(uso.get('vegetacao_regenerada_ha'))}.", BODY)]
    rows = [[_p('Grupo', CELL_BOLD), _p(str(antes), CELL_BOLD), _p(str(depois), CELL_BOLD)]]
    for group in uso.get('uso_por_grupo') or []:
        rows.append([_p(group['grupo']), _p(_ha(group['antes_ha'])), _p(_ha(group['depois_ha']))])
    if len(rows) > 1:
        parts += [Spacer(1, 4), _table(rows, [WIDTH - 7 * cm, 3.5 * cm, 3.5 * cm])]
    parts.append(_p('Fonte: MapBiomas Coleção 11 – cobertura e uso da terra (classificação de imagens Landsat, 30 m).',
                    SMALL))
    return parts


def _updates(report):
    rows = [[_p(h, CELL_BOLD) for h in ('Base', 'Atualizada em', 'Fonte')]]
    for row in report.get('atualizacao_das_bases') or []:
        when = row.get('atualizada_em') or 'não registrada'
        if row.get('observacao') and row.get('atualizada_em'):
            when += f" ({row['observacao'].rstrip('.').lower()})"
        rows.append([_p(row.get('base')), _p(when), _p(row.get('fonte'))])
    return _table(rows, [5.4 * cm, 3.6 * cm, WIDTH - 9 * cm])


def build_pdf(report, title, map_png=None, map_fonte=None, map_error=None):
    """PDF (bytes) do relatório `report` (saída de `queries.analysis_report`)."""
    buffer = io.BytesIO()
    generated = datetime.now(LOCAL_TZ).strftime('%d/%m/%Y %H:%M')

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(MARGIN, 1 * cm, _text(f'TerraView Tocantins · análise nº {report["analise_id"]} · '
                                                f'gerado em {generated}'))
        canvas.drawRightString(A4[0] - MARGIN, 1 * cm, f'Página {doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=1.6 * cm, title=_text(f'Relatório de sobreposição — {title}'),
                            author='TerraView Tocantins')
    story = [
        Paragraph(_text('Relatório de sobreposição'), TITLE),
        Paragraph(_text(title), SUBTITLE),
        _identification(report),
        Spacer(1, 8),
        _verdict(report),
    ]
    if report.get('aviso_bases_atualizadas'):
        story += [Spacer(1, 5), _p(report['aviso_bases_atualizadas'], SMALL)]
    story += [Paragraph('Mapa', H2), *_map(map_png, map_fonte, map_error)]
    story += [Paragraph('Perguntas do semáforo', H2), _checklist(report)]
    if report.get('bases_com_ocorrencia'):
        story += [Paragraph('Bases com ocorrência', H2), _bases(report)]
    residual = report.get('bases_so_com_encoste_minimo') or []
    if residual:
        story.append(_p(f"Só encostes menores que {_ha(report.get('limite_residual_ha'), 4)} (diferença de desenho "
                        f"entre os mapas): {', '.join(residual)}.", SMALL))
    rl = report.get('reserva_legal') or {}
    story += [Paragraph('Reserva Legal', H2), _p(
        f"Exigida (pela vegetação da área): {_ha(rl.get('exigida_ha'))}. Declarada no CAR: "
        f"{rl.get('declarada') or 'não informada'}."
        + (f" Déficit: {_ha(rl.get('deficit_ha'))}." if rl.get('deficit_ha') else ''), BODY)]
    if report.get('vegetacao_natural'):
        story.append(_p('Vegetação natural: ' + '; '.join(
            f"{v['tipo']} ({_ha(v['area_ha'])})" for v in report['vegetacao_natural']) + '.', BODY))
    story += [Paragraph('Uso do solo (MapBiomas)', H2), *_land_use(report)]
    if report.get('atualizacao_das_bases'):
        story += [Paragraph('Atualização das bases', H2), _updates(report)]
    links = report.get('links') or {}
    if links.get('resultado_na_plataforma'):
        story += [Spacer(1, 10), _p(f"Resultado completo na plataforma: {links['resultado_na_plataforma']}", SMALL)]
    story.append(_p('Este relatório cruza a área com as bases oficiais disponíveis na plataforma na data da análise. '
                    'Não substitui a consulta aos órgãos responsáveis nem a vistoria de campo.', SMALL))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
