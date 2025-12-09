import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Union
from extract_text_from_pdf import extrair_texto_pdf_pdfplumber

def get_name_document(texto: str) -> List[Dict[str, str]]:
    CPF_CNPJ_PATTERN = re.compile(r'(?:CPF|CNPJ)[:\s]*([\d./-]+)', re.IGNORECASE)
    NOME_PATTERN = re.compile(
        r'Nome[:\s]*(.*?)(?=(?:\s+(?:CPF|CNPJ)[:\s]|ÁREAS|$))',
        re.IGNORECASE | re.DOTALL,
    )
    cpfs_cnpjs = CPF_CNPJ_PATTERN.findall(texto or "")
    nomes = [n.strip() for n in NOME_PATTERN.findall(texto or "")]
    return [{"nome": nome, "documento": doc} for nome, doc in zip(nomes, cpfs_cnpjs)]


def _get_value(texto: str, inicio: str, fim: str, flags=0) -> Optional[str]:
    inicio_esc = re.escape(inicio)
    fim_esc = re.escape(fim)
    padrao = re.compile(f"{inicio_esc}\\s*(.*?)\\s*{fim_esc}", re.DOTALL | flags)
    match = padrao.search(texto or "")
    if match:
        conteudo = match.group(1)
        conteudo = re.sub(r"\\s+", " ", conteudo).strip()
        return conteudo
    return None


def _val_with_fallback(primary_text: str, inicio_opts: List[str], fim_opts: List[str], fallback_texts: List[str]) -> Optional[str]:
    flags = re.IGNORECASE
    for inicio in inicio_opts:
        for fim in fim_opts:
            v = _get_value(primary_text, inicio, fim, flags=flags)
            if v:
                return v
            for fb in fallback_texts:
                v = _get_value(fb, inicio, fim, flags=flags)
                if v:
                    return v
    return None

@dataclass
class ReciboInfo:
    car: Optional[str]
    nome_imovel_rural: Optional[str]
    modulos_fiscais: Optional[str]
    area_rural_consolidada: Optional[str]
    area_servidao_administrativa: Optional[str]
    remanescente_vegetacao_nativa: Optional[str]
    area_liquida_do_imovel: Optional[str]
    area_reserva_legal: Optional[str]
    area_preservacao_permanente: Optional[str]
    proprietarios: List[Dict[str, str]]

def parse_recibo(pagina2_texto: str, pagina3_texto: str, texto_total: Optional[str] = None) -> ReciboInfo:
    full_text = texto_total or ""
    def val3(inicios: Union[str, List[str]], fins: Union[str, List[str]]) -> Optional[str]:
        inicio_opts = [inicios] if isinstance(inicios, str) else inicios
        fim_opts = [fins] if isinstance(fins, str) else fins
        return _val_with_fallback(pagina3_texto or "", inicio_opts, fim_opts, [pagina2_texto or "", full_text])
    return ReciboInfo(
        car=val3("Registro no CAR:", "Data de Cadastro:").replace(".", ""),#tirando os pontos do car
        nome_imovel_rural=val3("Nome do Imóvel Rural:", "Município:"),
        modulos_fiscais=val3("Módulos Fiscais:", "Código"),
        area_rural_consolidada=val3(["Área Rural Consolidada", "Consolidada"], ["Área de Servidão Administrativa", "Área de Servidão"]),
        area_servidao_administrativa=val3("Área de Servidão Administrativa", "Remanescente de Vegetação Nativa"),
        remanescente_vegetacao_nativa=val3("Remanescente de Vegetação Nativa", "Área Líquida do Imóvel"),
        area_liquida_do_imovel=val3("Área Líquida do Imóvel", ["Reserva Legal", "Área de Reserva Legal"]),
        area_reserva_legal=val3("Área de Reserva Legal", "Área de Preservação Permanente"),
        area_preservacao_permanente=val3("Área de Preservação Permanente", "Área de Uso Restrito"),
        proprietarios=get_name_document(pagina2_texto or ""),
    )

def extrair_recibo_info(arquivo_pdf: Union[str, object]) -> ReciboInfo:
    texto_p2 = extrair_texto_pdf_pdfplumber(arquivo_pdf, pagina=2, deduplicar=True)
    texto_p3 = extrair_texto_pdf_pdfplumber(arquivo_pdf, pagina=3, deduplicar=True)
    texto_full = extrair_texto_pdf_pdfplumber(arquivo_pdf)
    return parse_recibo(texto_p2, texto_p3, texto_full)

def imprimir_info(info: ReciboInfo) -> None:
    for k, v in asdict(info).items():
        print(f"{k}: {v}")

# if __name__ == "__main__":
#     caminho = r"recibo.pdf"
#     info = extrair_recibo_info(caminho)
#     imprimir_info(info)

