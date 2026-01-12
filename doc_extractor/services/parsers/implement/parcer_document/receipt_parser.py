import re
from typing import Optional, List, Dict, Union

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


    def _get_value(self, texto: str, inicio: str, fim: str, flags=0) -> Optional[str]:
        inicio_esc = re.escape(inicio)
        fim_esc = re.escape(fim)
        padrao = re.compile(f"{inicio_esc}\\s*(.*?)\\s*{fim_esc}", re.DOTALL | flags)
        match = padrao.search(texto or "")
        if match:
            conteudo = match.group(1)
            conteudo = re.sub(r"\\s+", " ", conteudo).strip()
            return conteudo
        return None

    def _extract_value(self, text: str, start_opts: Union[str, List[str]], end_opts: Union[str, List[str]]) -> Optional[str]:
        starts = [start_opts] if isinstance(start_opts, str) else start_opts
        ends = [end_opts] if isinstance(end_opts, str) else end_opts
        
        for start in starts:
            for end in ends:
                val = self._get_value(text, start, end, re.IGNORECASE)
                if val:
                    return val
        return None

    def _parse_ha_value(self, s: Optional[str]) -> Optional[float]:
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

    def _format_ha(self, v: Optional[float]) -> Optional[str]:
        if v is None:
            return None
        return f"{v:.2f} ha"

    def _extract_page_text(self, text: str, page_number: int) -> str:
        pattern = fr"--- Página {page_number} ---\s+(.*?)(?=\s+--- Página \d+ ---|$)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def parse(self, text: str) -> ReceiptInfo:
        # Reconstruct page contexts to match legacy logic
        page2_text = self._extract_page_text(text, 2)
        page3_text = self._extract_page_text(text, 3)
        
        # Use page 3 for values, fallback to page 2 and full text
        # Logic from recibo.py: val3 uses page3 -> page2 -> full
        
        car_val = self._extract_value(page3_text, "Registro no CAR:", "Data de Cadastro:")
        # Fallback for CAR if not found on page 3 (though unlikely)
        if not car_val:
             car_val = self._extract_value(text, "Registro no CAR:", "Data de Cadastro:")

        nome_val = self._extract_value(page3_text, "Nome do Imóvel Rural:", "Município:")
        mod_val = self._extract_value(page3_text, "Módulos Fiscais:", "Código")
        
        # Areas are mostly on page 3
        arc_val = self._extract_value(page3_text, ["Área Rural Consolidada", "Consolidada"], ["Área de Servidão Administrativa", "Área de Servidão"])
        serv_val = self._extract_value(page3_text, "Área de Servidão Administrativa", "Remanescente de Vegetação Nativa")
        nativa_val = self._extract_value(page3_text, "Remanescente de Vegetação Nativa", "Área Líquida do Imóvel")
        liquida_val = self._extract_value(page3_text, "Área Líquida do Imóvel", ["Reserva Legal", "Área de Reserva Legal"])
        rl_val = self._extract_value(page3_text, "Área de Reserva Legal", "Área de Preservação Permanente")
        app_val = self._extract_value(page3_text, "Área de Preservação Permanente", "Área de Uso Restrito")
        
        # Fallbacks if Page 3 extraction failed (mimicking _val_with_fallback logic partially)
        # The legacy _val_with_fallback iterates: [page3] -> [page2, full]
        # My _extract_value only takes text. I should probably use a helper that takes the list of texts.
        
        def smart_extract(start, end):
             val = self._extract_value(page3_text, start, end)
             if val: return val
             val = self._extract_value(page2_text, start, end)
             if val: return val
             return self._extract_value(text, start, end)

        arc_val = smart_extract(["Área Rural Consolidada", "Consolidada"], ["Área de Servidão Administrativa", "Área de Servidão"])
        serv_val = smart_extract("Área de Servidão Administrativa", "Remanescente de Vegetação Nativa")
        nativa_val = smart_extract("Remanescente de Vegetação Nativa", "Área Líquida do Imóvel")
        liquida_val = smart_extract("Área Líquida do Imóvel", ["Reserva Legal", "Área de Reserva Legal"])
        rl_val = smart_extract("Área de Reserva Legal", "Área de Preservação Permanente")
        app_val = smart_extract("Área de Preservação Permanente", "Área de Uso Restrito")
        
        # Others that used val3
        car_val = smart_extract("Registro no CAR:", "Data de Cadastro:")
        nome_val = smart_extract("Nome do Imóvel Rural:", "Município:")
        mod_val = smart_extract("Módulos Fiscais:", "Código")

        a_apr = self._parse_ha_value(liquida_val)
        a_nat = self._parse_ha_value(nativa_val)
        a_arc = self._parse_ha_value(arc_val)
        
        antropizada_calc = None
        if a_apr is not None and a_nat is not None and a_arc is not None:
            antropizada_calc = self._format_ha(max(a_apr - a_nat - a_arc, 0.0))

        # Proprietarios strictly from Page 2 (or full text if page extraction fails, but legacy used page 2)
        # Legacy: get_name_document(pagina2_texto or "")
        proprietarios_text = page2_text if page2_text else text
        
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
            proprietarios=self._get_name_document(proprietarios_text),
        )