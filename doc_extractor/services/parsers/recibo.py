import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Union
from doc_extractor.services.parsers.contract.extract_document_contract import ExtractDocumentBase
from doc_extractor.services.pdf_engine import extrair_texto_pdf_pdfplumber
from doc_extractor.services.parsers.database.receipt_info import ReceiptInfo

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

def _parse_ha_value(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"[\d.,]+", s)
    if not m:
        return None
    num = m.group(0)
    num = num.replace(".", "")
    num = num.replace(",", ".")
    try:
        return float(num)
    except Exception:
        return None

def _format_ha(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    return f"{v:.2f} ha"

def parse_recibo(pagina2_texto: str, pagina3_texto: str, texto_total: Optional[str] = None) -> ReceiptInfo:
    full_text = texto_total or ""
    # print(full_text)
    def val3(inicios: Union[str, List[str]], fins: Union[str, List[str]]) -> Optional[str]:
        inicio_opts = [inicios] if isinstance(inicios, str) else inicios
        fim_opts = [fins] if isinstance(fins, str) else fins
        return _val_with_fallback(pagina3_texto or "", inicio_opts, fim_opts, [pagina2_texto or "", full_text])
    car_val = val3("Registro no CAR:", "Data de Cadastro:")
    nome_val = val3("Nome do Imóvel Rural:", "Município:")
    mod_val = val3("Módulos Fiscais:", "Código")
    arc_val = val3(["Área Rural Consolidada", "Consolidada"], ["Área de Servidão Administrativa", "Área de Servidão"])
    serv_val = val3("Área de Servidão Administrativa", "Remanescente de Vegetação Nativa")
    nativa_val = val3("Remanescente de Vegetação Nativa", "Área Líquida do Imóvel")
    liquida_val = val3("Área Líquida do Imóvel", ["Reserva Legal", "Área de Reserva Legal"])
    rl_val = val3("Área de Reserva Legal", "Área de Preservação Permanente")
    app_val = val3("Área de Preservação Permanente", "Área de Uso Restrito")
    a_apr = _parse_ha_value(liquida_val)
    a_nat = _parse_ha_value(nativa_val)
    a_arc = _parse_ha_value(arc_val)
    antropizada_calc = None
    if a_apr is not None and a_nat is not None and a_arc is not None:
        antropizada_calc = _format_ha(max(a_apr - a_nat - a_arc, 0.0))

    return ReceiptInfo(
        car=(car_val or "").replace(".", ""),
        nome_imovel_rural=nome_val,
        modulos_fiscais=mod_val,
        area_rural_consolidada=arc_val,
        area_servidao_administrativa=serv_val,
        remanescente_vegetacao_nativa=nativa_val,
        area_liquida_do_imovel=liquida_val,
        area_reserva_legal=rl_val,
        area_preservacao_permanente=app_val,
        area_antropizada=antropizada_calc,
        proprietarios=get_name_document(pagina2_texto or ""),
    )

def extrair_recibo_info(arquivo_pdf: Union[str, object], extractor: ExtractDocumentBase) -> ReceiptInfo:
    texto_p2 = extractor.extract_text(arquivo_pdf, page=2, deduplicate=True)
    texto_p3 = extractor.extract_text(arquivo_pdf, page=3, deduplicate=True)
    texto_full = extractor.extract_text(arquivo_pdf, deduplicate=True)
    return parse_recibo(texto_p2, texto_p3, texto_full)

def imprimir_info(info: ReceiptInfo) -> None:
    for k, v in asdict(info).items():
        print(f"{k}: {v}")

# if __name__ == "__main__":
#     caminho = r"recibo.pdf"
#     info = extrair_recibo_info(caminho)
#     imprimir_info(info)
