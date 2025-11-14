from typing import Any, Dict, List, Optional, Tuple
from car_system.services.process_data.sicar_process import SicarProcess
from car_system.services.read_files.sicar_loader import SicarRecordLoader

from environmental_layers.services.precess_data.zoning_loader_process import ZoningProcess

from environmental_layers.services.precess_data.phytoecology_process import PhytoecologyProcess
from environmental_layers.services.precess_data.protection_area_process import ProtectionAreaProcess
from environmental_layers.services.load_data.zoning_loader import ZoningLoader
from environmental_layers.services.load_data.phytoecology_loader import PhytoecologyLoader
from environmental_layers.services.load_data.protection_area_loader import ProtectionAreaLoader
from kernel.service.geometry_overlap_service import GeometryOverlapService
from logica_sobreposicao import VerificadorSobreposicao


class SearchAll:
    """Orquestra a busca de sobreposições em todas as bases de dados.

    Responsável por:
    - Carregar dados das bases (SICAR, Zoneamento, Fitoecologias, APAs)
    - Processar sobreposições com verificador
    - Consolidar e padronizar o resultado para a UI
    """

    def __init__(self):
        # Instância única do verificador de sobreposição
        self.verifier = VerificadorSobreposicao()
        # Processadores por base de dados
        self.sicar_process = SicarProcess(self.verifier)
        self.zoning_process = ZoningProcess(self.verifier)
        self.phyto_process = PhytoecologyProcess(self.verifier)
        self.protection_area_process = ProtectionAreaProcess(self.verifier)

    def execute(self, coordenadas, excluir_car=None):
        """Executa a análise completa de sobreposições para o WKT informado.

        Parâmetros:
        - coordenadas: WKT do polígono analisado
        - excluir_car: número de CAR a ser desconsiderado na base de imóveis
        """
        polygon_wkt: str = coordenadas

        # Cálculo de área do polígono (ha)
        area_size_ha: Optional[float] = self._compute_area_size_ha(polygon_wkt)

        # Carregar dados das bases
        data: Dict[str, List[Dict[str, Any]]] = self._load_data(excluir_car)

        # Processar todas as bases de dados e obter lista de resultados por base
        results_by_base: List[Dict[str, Any]] = self._process_all_bases(polygon_wkt, data)

        # Agregar métricas globais a partir das bases
        all_found_areas, total_not_evaluated, total_overlaps = self._aggregate_base_results(
            results_by_base
        )

        # Resumo das quantidades por base (mantém chaves esperadas pela UI)
        summary_bases: Dict[str, int] = self._build_summary(data)

        # Montar dicionário final (mantém compatibilidade com templates atuais)
        final_result: Dict[str, Any] = self._build_final_result(
            results_by_base,
            all_found_areas,
            total_not_evaluated,
            total_overlaps,
            area_size_ha,
            summary_bases,
        )

        return final_result

    def _process_all_bases(self, polygon_wkt: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Processa todas as bases e retorna a lista de resultados por base."""
        results_by_base: List[Dict[str, Any]] = []

        # SICAR / Imóveis
        results_by_base.append(
            self.sicar_process.process(
                polygon_wkt, data["imoveis"], "Base de Dados Sicar"
            )
        )

        # Zoneamento
        results_by_base.append(
            self.zoning_process.process(
                polygon_wkt, data["zoneamento"], "Base de Dados de Zoneamento"
            )
        )

        # Fitoecologias: normaliza entrada para tuplas (wkt, nome)
        phyto_input: List[Tuple[str, str]] = [
            (item.get("wkt"), item.get("nome_fitoecologia"))
            for item in data["fitoecologias"]
        ]
        results_by_base.append(
            self.phyto_process.process(
                polygon_wkt, phyto_input, "Base de Dados de Fitoecologias"
            )
        )

        # APAs
        results_by_base.append(
            self.protection_area_process.process(
                polygon_wkt, data["apas"], "Base de Dados de APAs"
            )
        )

        return results_by_base

    def _aggregate_base_results(
        self, results_by_base: List[Dict[str, Any]]
    ):
        """Agrega áreas encontradas e contadores globais a partir das bases."""
        all_found_areas: List[Dict[str, Any]] = []
        total_not_evaluated: int = 0
        total_overlaps: int = 0

        for base_result in results_by_base:
            all_found_areas.extend(base_result["areas_encontradas"])
            total_not_evaluated += base_result["quantidade_nao_avaliados"]
            total_overlaps += base_result["total_areas_com_sobreposicao"]

        return all_found_areas, total_not_evaluated, total_overlaps

    def _build_summary(self, data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
        """Cria resumo de quantidades por base (mantém chaves em português)."""
        return {
            "imoveis": len(data["imoveis"]),
            "zoneamento": len(data["zoneamento"]),
            "fitoecologias": len(data["fitoecologias"]),
            "apas": len(data["apas"]),
        }

    def _build_final_result(
        self,
        results_by_base: List[Dict[str, Any]],
        all_found_areas: List[Dict[str, Any]],
        total_not_evaluated: int,
        total_overlaps: int,
        area_size_ha: Optional[float],
        summary_bases: Dict[str, int],
    ) -> Dict[str, Any]:
        """Monta o dicionário final esperado pela UI (mantém chaves atuais)."""
        return {
            "resultados_por_base": results_by_base,
            "areas_encontradas": all_found_areas,
            "quantidade_nao_avaliados": total_not_evaluated,
            "total_areas_com_sobreposicao": total_overlaps,
            "tamanho_area": area_size_ha,
            "resumo_bases": summary_bases,
        }

    def _compute_area_size_ha(self, polygon_wkt: str) -> Optional[float]:
        """Calcula a área do polígono em hectares, com tratamento seguro de erros."""
        try:
            from helpers.return_area_coordinates import calculate_area_ha
            if polygon_wkt and str(polygon_wkt).strip():
                return calculate_area_ha(polygon_wkt)
        except Exception as e:
            print(f"Erro ao calcular a área do polígono. {e}")
            return None
        return None

    def _load_data(self, excluir_car=None) -> Dict[str, List[Dict[str, Any]]]:
        """Carrega dados de todas as bases necessárias para a análise."""
        properties_data = SicarRecordLoader.load(car=excluir_car)
        zoning_data = ZoningLoader.load()
        phyto_data = PhytoecologyLoader.load()
        protection_area_data = ProtectionAreaLoader.load()
        
        print("Dados carregados das bases de dados.")
        
        return {
            "imoveis": properties_data,
            "zoneamento": zoning_data,
            "fitoecologias": phyto_data,
            "apas": protection_area_data,
        }
