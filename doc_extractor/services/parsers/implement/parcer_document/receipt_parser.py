import re
from typing import Optional, List, Dict

from doc_extractor.services.parsers.database.receipt_info import ReceiptInfo
from doc_extractor.services.parsers.contract.parser_document_contract import ParserDocumentBase

class ReceiptParser(ParserDocumentBase):

    def _get_name_document(self, texto: str) -> List[Dict[str, str]]:
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

    def parse(self, text: str) -> ReceiptInfo:
        pass