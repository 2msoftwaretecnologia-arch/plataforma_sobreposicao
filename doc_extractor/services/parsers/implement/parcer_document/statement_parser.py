import re
from typing import Optional

from doc_extractor.services.parsers.database.statement_info import StatementInfo
from doc_extractor.services.parsers.contract.parser_document_contract import ParserDocumentBase

class StatementParser(ParserDocumentBase):

    def _get_car(self, text: str) -> Optional[str]:
        pat = re.compile(r"\b[A-Z]{2}-\d{1,15}-[A-F0-9]{32}\b")
        m = pat.search(text)
        return m.group(0) if m else None
    
    def _get_last_retification_date(self, text: str) -> Optional[str]:
        dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text)
        return dates[-1] if dates else None

    def _get_block_reserva_legal_averbada(self, text: str) -> Optional[str]:
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

    def _get_value(self, texto: str, inicio: str, fim: str, flags=0) -> Optional[str]:
        inicio_esc = re.escape(inicio)
        fim_esc = re.escape(fim)
        padrao = re.compile(f"{inicio_esc}\\s*(.*?)\\s*{fim_esc}", re.DOTALL | flags)
        match = padrao.search(texto)
        if match:
            conteudo = match.group(1)
            conteudo = re.sub(r"\s+", " ", conteudo).strip()
            return conteudo
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
    
    def parse(self, text: str) -> StatementInfo:
        bloco = self._get_block_reserva_legal_averbada(text) or text

        def val(inicio: str, fim: str) -> Optional[str]:
            v = self._get_value(bloco, inicio, fim, flags=re.IGNORECASE)
            if v is None:
                v = self._get_value(text, inicio, fim, flags=re.IGNORECASE)
            return v
            
        car_val = self._get_car(text)
        data_val = self._get_last_retification_date(text)
        ext_val = val("Condição Externa:", "Situação")
        mod_val = val("Módulos Fiscais:", "Coordenadas")
        reg_val = val("Situação do Cadastro:", "Informações")
        nativa_val = val("Área de Remanescente de Vegetação Nativa", "Área Rural Consolidada")
        arc_val = val("Área Rural Consolidada", "Área de Servidão Administrativa")
        serv_val = val("Área de Servidão Administrativa", "CAR")
        rl_averb_val = val("12.651/2012", "Informação")
        rl_aprov_val = val("Área de Reserva Legal Aprovada não Averbada", "Área de Reserva Legal Proposta")
        rl_prop_val = val("Área de Reserva Legal Proposta", "Total de Reserva Legal Declarada pelo Proprietário/Possuidor")
        rl_total_val = val("Total de Reserva Legal Declarada pelo Proprietário/Possuidor", "Áreas de Preservação Permanente (APP)")
        app_total_val = val("\nAPP", "APP em Área Rural Consolidada")
        app_arc_val = val("APP em Área Rural Consolidada", "APP em Área de Remanescente de Vegetação Nativa")
        app_nat_val = val("APP em Área de Remanescente de Vegetação Nativa", "Áreas de Uso Restrito")
        passivo_val = val("Passivo / Excedente de Reserva Legal", "Área de Reserva Legal a recompor")
        rl_recomp_val = val("Área de Reserva Legal a recompor", "Áreas de Preservação Permanente a recompor")
        app_recomp_val = val("Áreas de Preservação Permanente a recompor", "Área de Uso Restrito a recompor")

        a_apr = self._parse_ha_value(app_total_val)
        a_nat = self._parse_ha_value(nativa_val)
        a_arc = self._parse_ha_value(arc_val)
        antropizada_calc = None
        if a_apr is not None and a_nat is not None and a_arc is not None:
            antropizada_calc = self._format_ha(max(a_apr - a_nat - a_arc, 0.0))

        return StatementInfo(
            car=car_val,
            data_retificacao=data_val,
            external_condicion=ext_val,
            tax_modules=mod_val,
            registration_status=reg_val,
            native_vegetation_remmant_area=nativa_val,
            area_rural_consolidada=arc_val,
            area_servidao_admistrativa=serv_val,
            area_Reserva_Legal_Averbada_referente_Art_30_codigo_florestal=rl_averb_val,
            area_Reserva_Legal_Aprovada_nao_Averbada=rl_aprov_val,
            area_reserva_legal_proposta=rl_prop_val,
            total_reserva_legal_declarada_pelo_proprietario_possuidor=rl_total_val,
            area_app=app_total_val,
            app_em_area_rural_consolidada=app_arc_val,
            app_em_area_remanescente_vegetacao_nativa=app_nat_val,
            passivo_ou_excedente_de_reserva_legal=passivo_val,
            area_reserva_legal_a_recompor=rl_recomp_val,
            area_de_preservacao_permanente_a_recompor=app_recomp_val,
            area_antropizada=antropizada_calc,
        )