import re
from dataclasses import dataclass, asdict
from typing import Optional
from extract_text_from_pdf import extrair_texto_pdf_pdfplumber

def _get_car(text: str) -> Optional[str]:
    pat = re.compile(r"\b[A-Z]{2}-\d{1,15}-[A-F0-9]{32}\b")
    m = pat.search(text)
    return m.group(0) if m else None

def _get_last_retification_date(text: str) -> Optional[str]:
    dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text)
    return dates[-1] if dates else None

def _get_block_reserva_legal_averbada(text: str) -> Optional[str]:
    inicio = "Área de Reserva Legal Averbada"
    fim = "Área de Reserva Legal Aprovada não Averbada"
    posicoes_inicio = []
    pos = -1
    while True:
        pos = text.find(inicio, pos + 1)
        if pos == -1:
            break
        posicoes_inicio.append(pos)
    if len(posicoes_inicio) < 2:
        return None
    pos_fim = text.find(fim)
    if pos_fim == -1:
        return None
    inicio_segunda = posicoes_inicio[1] + len(inicio)
    if inicio_segunda > pos_fim:
        return None
    return text[inicio_segunda:pos_fim].strip()

def _get_value(texto: str, inicio: str, fim: str, flags=0) -> Optional[str]:
    inicio_esc = re.escape(inicio)
    fim_esc = re.escape(fim)
    padrao = re.compile(f"{inicio_esc}\\s*(.*?)\\s*{fim_esc}", re.DOTALL | flags)
    match = padrao.search(texto)
    if match:
        conteudo = match.group(1)
        conteudo = re.sub(r"\s+", " ", conteudo).strip()
        return conteudo
    return None

@dataclass
class DemonstrativoInfo:
    car: Optional[str]
    data_retificacao: Optional[str]
    external_condicion: Optional[str]
    tax_modules: Optional[str]
    registration_status: Optional[str]
    native_vegetation_remmant_area: Optional[str]
    area_rural_consolidada: Optional[str]
    area_servidao_admistrativa: Optional[str]
    area_Reserva_Legal_Averbada_referente_Art_30_codigo_florestal: Optional[str]
    area_Reserva_Legal_Aprovada_nao_Averbada: Optional[str]
    area_reserva_legal_proposta: Optional[str]
    total_reserva_legal_declarada_pelo_proprietario_possuidor: Optional[str]
    area_app: Optional[str]
    app_em_area_rural_consolidada: Optional[str]
    app_em_area_remanescente_vegetacao_nativa: Optional[str]
    passivo_ou_excedente_de_reserva_legal: Optional[str]
    area_reserva_legal_a_recompor: Optional[str]
    area_de_preservacao_permanente_a_recompor: Optional[str]

def parse_demonstrativo(text: str) -> DemonstrativoInfo:
    bloco = _get_block_reserva_legal_averbada(text) or text
    def val(inicio: str, fim: str) -> Optional[str]:
        v = _get_value(bloco, inicio, fim, flags=re.IGNORECASE)
        if v is None:
            v = _get_value(text, inicio, fim, flags=re.IGNORECASE)
        return v
    return DemonstrativoInfo(
        car=_get_car(text),
        data_retificacao=_get_last_retification_date(text),
        external_condicion=val("Condição Externa:", "Situação"),
        tax_modules=val("Módulos Fiscais:", "Coordenadas"),
        registration_status=val("Situação do Cadastro:", "Informações"),
        native_vegetation_remmant_area=val("Área de Remanescente de Vegetação Nativa", "Área Rural Consolidada"),
        area_rural_consolidada=val("Área Rural Consolidada", "Área de Servidão Administrativa"),
        area_servidao_admistrativa=val("Área de Servidão Administrativa", "CAR"),
        area_Reserva_Legal_Averbada_referente_Art_30_codigo_florestal=val("12.651/2012", "Informação"),
        area_Reserva_Legal_Aprovada_nao_Averbada=val("Área de Reserva Legal Aprovada não Averbada", "Área de Reserva Legal Proposta"),
        area_reserva_legal_proposta=val("Área de Reserva Legal Proposta", "Total de Reserva Legal Declarada pelo Proprietário/Possuidor"),
        total_reserva_legal_declarada_pelo_proprietario_possuidor=val("Total de Reserva Legal Declarada pelo Proprietário/Possuidor", "Áreas de Preservação Permanente (APP)"),
        area_app=val("\nAPP", "APP em Área Rural Consolidada"),
        app_em_area_rural_consolidada=val("APP em Área Rural Consolidada", "APP em Área de Remanescente de Vegetação Nativa"),
        app_em_area_remanescente_vegetacao_nativa=val("APP em Área de Remanescente de Vegetação Nativa", "Áreas de Uso Restrito"),
        passivo_ou_excedente_de_reserva_legal=val("Passivo / Excedente de Reserva Legal", "Área de Reserva Legal a recompor"),
        area_reserva_legal_a_recompor=val("Área de Reserva Legal a recompor", "Áreas de Preservação Permanente a recompor"),
        area_de_preservacao_permanente_a_recompor=val("Áreas de Preservação Permanente a recompor", "Área de Uso Restrito a recompor"),
    )

def imprimir_info(info: DemonstrativoInfo) -> None:
    for k, v in asdict(info).items():
        print(f"{k}: {v}")

# if __name__ == "__main__":
#     import sys
#     caminhos = sys.argv[1:] or [r"C:\Users\2mbet\Downloads\Demonstrativo_TO-1718204-74EAC3D70B364C78B84EE5D2738C0A6D.pdf"]
#     for i, caminho in enumerate(caminhos, 1):
#         texto = extrair_texto_pdf_pdfplumber(caminho)
#         info = parse_demonstrativo(texto)
#         print(f"Arquivo {i}: {caminho}")
#         imprimir_info(info)
