from dataclasses import dataclass
from typing import Optional

@dataclass
class StatementInfo:
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
    area_antropizada: Optional[str]