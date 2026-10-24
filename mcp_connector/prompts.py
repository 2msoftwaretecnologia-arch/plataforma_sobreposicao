"""Prompts prontos do conector (aparecem no menu do conector no Claude).

Cada prompt recebe a área (CAR, parcela do SIGEF ou número de uma análise) e
diz ao assistente quais ferramentas chamar e como montar o texto, para a
equipe gerar pareceres e resumos sempre no mesmo formato.
"""
from typing import Annotated

from pydantic import Field

Area = Annotated[str, Field(description='Número do CAR, código da parcela do SIGEF ou número da análise (analise_id).')]

COMMON = (
    'Use o conector TerraView Tocantins. Área: {area}. Se for só um número, é o analise_id de uma análise já feita; '
    'se começar com "TO-", é um CAR (analisar_car); senão, o código de uma parcela do SIGEF '
    '(analisar_parcela_sigef). A plataforma reaproveita sozinha uma análise recente da mesma área.\n\n'
    'Regras: use só o que as ferramentas devolverem, sem inventar dados; itens com "residual": true são '
    'diferença de desenho entre os mapas, não conflito; cite a fonte de toda imagem (satélite/sensor, data da '
    'captura, resolução e provedor, de fonte_imagem) e a data de atualização das bases '
    '(atualizacao_das_bases do relatorio_analise); se houver aviso_bases_atualizadas, diga isso no texto. '
    'Mostre os links devolvidos.\n\n'
)

PARECER_BANCO = COMMON + (
    'Tarefa: redigir um parecer técnico de conformidade socioambiental do imóvel para análise de crédito rural.\n'
    'Passos: relatorio_analise; mapa_analise (bases de alerta e atenção); imagem_historica com ano=2008 e '
    'comparar_com_atual=true; arquivos_analise.\n'
    'Estrutura, em tom formal:\n'
    '1. Identificação do imóvel (CAR, município, área, coordenada central, nº e data da análise).\n'
    '2. Conclusão: o veredito em uma frase.\n'
    '3. Restrições que impedem ou condicionam o crédito: embargo do IBAMA, desmatamento após 22/07/2008 '
    '(PRODES/MapBiomas), terra indígena, território quilombola, unidade de conservação de proteção integral.\n'
    '4. Pontos para conferir (nível "atencao").\n'
    '5. Reserva Legal e APP.\n'
    '6. Uso do solo e imagens: 2008 × atual.\n'
    '7. Fontes: bases consultadas com a data de atualização de cada uma, e a fonte de cada imagem.\n'
    '8. Anexos: link do relatório em PDF, do mapa e do KML das sobreposições.\n'
    'Termine lembrando que o parecer se baseia nas bases oficiais disponíveis na plataforma na data da análise e '
    'não substitui a consulta aos órgãos nem a vistoria.'
)

DUE_DILIGENCE = COMMON + (
    'Tarefa: due diligence socioambiental e fundiária para a compra do imóvel.\n'
    'Passos: relatorio_analise; detalhes_analise das bases do SICAR, do SIGEF, de embargos e de desmatamento que '
    'tiverem ocorrência (para listar vizinhos sobrepostos, proprietários, datas e números dos autos); '
    'mapa_analise com base="todas"; imagem_historica com ano=2008.\n'
    'Monte: (a) tabela de riscos (risco, evidência, gravidade alta/média/baixa, o que fazer), cobrindo '
    'sobreposição com outros CARs e com parcelas do SIGEF (conflito de limites ou de titularidade), embargos, '
    'desmatamento, terra indígena, quilombola, unidade de conservação, assentamento, déficit de Reserva Legal; '
    '(b) lista de documentos a pedir ao vendedor (matrícula atualizada, CCIR, ITR, recibo e demonstrativo do '
    'CAR, certificação SIGEF/georreferenciamento, certidões negativas do IBAMA e do órgão ambiental do '
    'Tocantins); (c) conclusão: seguir, seguir com ressalvas ou não seguir, e por quê.'
)

CODIGO_FLORESTAL = COMMON + (
    'Tarefa: checklist do Código Florestal com o marco temporal de 22/07/2008.\n'
    'Passos: relatorio_analise; imagem_historica com ano=2008 e comparar_com_atual=true; mapa_uso_solo com '
    'comparar_com_2008=true.\n'
    'Compare a vegetação nativa de 2008 com a atual (relatorio_analise.uso_do_solo_mapbiomas e as classes de '
    'mapa_uso_solo) e diga se a abertura parece anterior (área consolidada) ou posterior a 2008 (supressão a '
    'regularizar), apontando o que se vê nas duas imagens. Avalie a Reserva Legal (exigida × declarada); se não '
    'houver a declarada, ofereça o link_envio do tipo "demonstrativo" para o usuário mandar o PDF do CAR. '
    'Comente APP e a situação do CAR. Entregue uma tabela "item | situação | evidência | providência".'
)

RESUMO_CLIENTE = COMMON + (
    'Tarefa: resumo do resultado para o produtor rural, em linguagem simples, para mandar por WhatsApp.\n'
    'Passos: relatorio_analise e arquivos_analise.\n'
    'No máximo 8 linhas, sem termos técnicos nem siglas sem explicar: o que foi verificado, se está tudo certo '
    'ou o que precisa de atenção, o que fazer em seguida e o link do relatório em PDF. Sem emojis em excesso.'
)


def register_prompts(server):
    @server.prompt(name='parecer_para_banco', title='Parecer socioambiental para crédito rural',
                   description='Parecer formal de conformidade do imóvel para o banco, com mapas 2008 × atual e fontes.')
    def parecer_para_banco(area: Area) -> str:
        return PARECER_BANCO.format(area=area)

    @server.prompt(name='due_diligence_compra', title='Due diligence para compra de imóvel',
                   description='Riscos ambientais e fundiários, documentos a pedir e conclusão para quem vai comprar.')
    def due_diligence_compra(area: Area) -> str:
        return DUE_DILIGENCE.format(area=area)

    @server.prompt(name='checklist_codigo_florestal', title='Checklist do Código Florestal (marco de 2008)',
                   description='Vegetação em 2008 × hoje, área consolidada, Reserva Legal e APP.')
    def checklist_codigo_florestal(area: Area) -> str:
        return CODIGO_FLORESTAL.format(area=area)

    @server.prompt(name='resumo_para_cliente', title='Resumo para o cliente',
                   description='Resultado em linguagem simples, curto, para mandar ao produtor.')
    def resumo_para_cliente(area: Area) -> str:
        return RESUMO_CLIENTE.format(area=area)
