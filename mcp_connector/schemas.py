"""Formato das respostas das ferramentas (o `outputSchema` do MCP).

Com o esquema, o Claude e o ChatGPT sabem de antemão que campos cada
ferramenta devolve. Os modelos aceitam campos a mais (`extra='allow'`) e
quase tudo é opcional: o esquema descreve as respostas de `queries.py`, não
as limita, e uma resposta fora dele não pode derrubar a ferramenta.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra='allow')


class Links(Schema):
    resultado_na_plataforma: str | None = Field(None, description='Página do resultado na plataforma (pede login).')
    relatorio_para_imprimir: str | None = Field(None, description='Relatório para imprimir na plataforma (pede login).')
    relatorio_pdf: str | None = Field(None, description='PDF do relatório, por link assinado (sem login).')


class ItemResumo(Schema):
    descricao: str = ''
    area_ha: float | None = None
    residual: bool | None = Field(None, description='Encoste menor que limite_residual_ha (diferença de desenho).')


class BaseResumo(Schema):
    base: str
    nivel: str = Field(description='"alerta", "atencao" ou "info".')
    quantidade: int
    area_ha: float
    percentual_do_imovel: float | None = None
    itens: list[ItemResumo] = []
    itens_nao_listados: int | None = None


class AnaliseResumo(Schema):
    analise_id: int
    data: str
    tipo: str
    car_ou_identificacao: str | None = None
    municipio: str | None = None
    uf: str | None = None
    area_imovel_ha: float | None = None
    total_sobreposicoes: int = 0
    bases_com_sobreposicao: list[BaseResumo] = []
    bases_sem_sobreposicao: list[str] = []
    limite_residual_ha: float | None = None
    links: Links | None = None
    aviso: str | None = None
    reaproveitada: bool | None = Field(None, description='true quando uma análise recente igual foi reaproveitada.')


class PontoSemImovel(Schema):
    ponto: dict[str, float]
    municipio: str | None = None
    imovel_encontrado: bool = False
    mensagem: str


class ItemDetalhe(Schema):
    descricao: str = ''
    area_ha: float | None = None
    fora_de_unidade: bool | None = None
    atributos: dict[str, Any] = {}


class DetalhesBase(Schema):
    analise_id: int
    base: str
    nivel: str
    o_que_e: str | None = None
    o_que_significa_se_encontrado: str | None = None
    quantidade: int
    area_total_ha: float
    itens: list[ItemDetalhe] = []
    itens_nao_listados: int | None = None


class AnaliseDoHistorico(Schema):
    analise_id: int
    data: str
    tipo: str
    car_ou_identificacao: str | None = None
    municipio: str | None = None
    area_ha: float | None = None
    sobreposicoes: int | None = None
    sucesso: bool = True
    erro: str | None = None


class ListaAnalises(Schema):
    pagina: int
    total_paginas: int
    total_analises: int
    analises: list[AnaliseDoHistorico] = []


class ImovelNoPonto(Schema):
    car: str
    situacao: str | None = None
    area_ha: float | None = None
    ultima_atualizacao: str | None = None


class ParcelaNoPonto(Schema):
    codigo_parcela: str | None = None
    codigo_imovel: str | None = None
    nome: str | None = None
    situacao: str | None = None
    area_ha: float | None = None


class PontoLocalizado(Schema):
    latitude: float
    longitude: float
    municipio: str | None = None
    imoveis_sicar: list[ImovelNoPonto] | None = None
    parcelas_sigef: list[ParcelaNoPonto] | None = None


class Pergunta(Schema):
    pergunta: str
    status: str = Field(description='"alerta", "atencao", "ok", "info" ou "sem_dado".')
    resposta: str
    explicacao: str | None = None


class BaseRelatorio(Schema):
    base: str | None = None
    titulo: str | None = None
    nivel: str | None = None
    o_que_e: str | None = None
    o_que_significa: str | None = None
    area_ha: float | None = None
    percentual_do_imovel: float | None = None
    itens: list[ItemResumo] = []


class ReservaLegal(Schema):
    exigida_ha: float | None = None
    declarada: str | None = None
    deficit_ha: float | None = None
    avaliada: bool | None = None


class Localizacao(Schema):
    latitude: float
    longitude: float
    google_maps: str | None = None


class AtualizacaoBase(Schema):
    base: str
    atualizada_em: str | None = Field(None, description='Data da última atualização da base (dd/mm/aaaa hh:mm).')
    fonte: str | None = None
    observacao: str | None = None


class Relatorio(Schema):
    analise_id: int
    data: str
    car: str | None = None
    nome_imovel: str | None = None
    proprietarios: list[Any] = []
    municipio: str | None = None
    uf: str | None = None
    localizacao: Localizacao | None = None
    area_imovel_ha: float | None = None
    veredito: str
    alertas: int
    pontos_de_atencao: int
    perguntas: list[Pergunta] = []
    bases_com_ocorrencia: list[BaseRelatorio] = []
    bases_so_com_encoste_minimo: list[str] = []
    bases_sem_ocorrencia: list[str] = []
    limite_residual_ha: float | None = None
    reserva_legal: ReservaLegal | None = None
    vegetacao_natural: list[dict[str, Any]] = []
    municipios: list[str] = []
    uso_do_solo_mapbiomas: dict[str, Any] = {}
    atualizacao_das_bases: list[AtualizacaoBase] = []
    aviso_bases_atualizadas: str | None = None
    links: Links | None = None


class ParDeArquivos(Schema):
    kml: str
    shp: str


class ArquivosDaBase(ParDeArquivos):
    base: str
    itens: int


class ArquivosAnalise(Schema):
    analise_id: int
    validade: str
    relatorio_pdf: str | None = None
    imovel: ParDeArquivos
    mapa_png: str
    todas_as_sobreposicoes: ParDeArquivos | None = None
    por_base: list[ArquivosDaBase] | None = None
    observacao: str | None = None


class LinkEnvio(Schema):
    codigo: str
    link_envio: str
    aceita: str
    validade: str
    proximo_passo: str


class ResultadoEnvio(Schema):
    codigo: str
    situacao: str = Field(description='"aguardando", "processando", "concluido", "erro" ou "expirado".')
    tipo: str | None = None
    arquivo: str | None = None
    mensagem: str | None = None
    analise: AnaliseResumo | None = None
