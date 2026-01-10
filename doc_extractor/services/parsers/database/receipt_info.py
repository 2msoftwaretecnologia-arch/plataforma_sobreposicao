from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class ReceiptInfo:
    car: Optional[str]
    nome_imovel_rural: Optional[str]
    modulos_fiscais: Optional[str]
    area_rural_consolidada: Optional[str]
    area_servidao_administrativa: Optional[str]
    remanescente_vegetacao_nativa: Optional[str]
    area_liquida_do_imovel: Optional[str]
    area_reserva_legal: Optional[str]
    area_preservacao_permanente: Optional[str]
    area_antropizada: Optional[str]
    proprietarios: List[Dict[str, str]]