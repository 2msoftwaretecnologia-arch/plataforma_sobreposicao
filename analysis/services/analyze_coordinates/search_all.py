from typing import Any, Dict, List, Optional, Tuple
import time
from analysis.services.analyze_coordinates.helpers_service.load_all_data_service import LoadAllDataService
from analysis.services.analyze_coordinates.helpers_service.process_all_data_service import ProcessAllDataService
from analysis.services.analyze_coordinates.helpers_service.search.final_result_builder import FinalResultBuilder
from analysis.services.analyze_coordinates.helpers_service.search.processor_registry import ProcessorRegistry
from analysis.services.analyze_coordinates.helpers_service.search.result_aggregator import ResultAggregator
from car_system.services.process_data.sicar_process import SicarProcess
from car_system.services.read_files.sicar_loader import SicarRecordLoader

from environmental_layers.services.precess_data.zoning_loader_process import ZoningProcess

from environmental_layers.services.precess_data.phytoecology_process import PhytoecologyProcess
from environmental_layers.services.precess_data.protection_area_process import ProtectionAreaProcess
from environmental_layers.services.load_data.zoning_loader import ZoningLoader
from environmental_layers.services.load_data.phytoecology_loader import PhytoecologyLoader
from environmental_layers.services.load_data.protection_area_loader import ProtectionAreaLoader
from kernel.service.geometry_overlap_service import OverlapChecker
from kernel.utils import calculate_area_ha


class SearchAll:
    """Orquestra a busca de sobreposições em todas as bases de dados.

    Responsável por:
    - Carregar dados das bases (SICAR, Zoneamento, Fitoecologias, APAs)
    - Processar sobreposições com verificador
    - Consolidar e padronizar o resultado para a UI
    """

    def __init__(self):
        # Instância única do verificador de sobreposição
        self.verifier = OverlapChecker()
        
        # Carregamento inicial de dados (evita carregar múltiplas vezes)
        self.load_all_data_service = LoadAllDataService()
        self.processors_all_data_service = ProcessAllDataService()
        self.processor_registry = ProcessorRegistry(self.verifier)
        self.result_aggregator = ResultAggregator()
        self.final_result_builder = FinalResultBuilder()

    def execute(self, geometry, car=None):
        """Executa a análise completa de sobreposições para o WKT informado.

        Parâmetros:
        - geometry: WKT do polígono analisado
        - car: número de CAR a ser desconsiderado na base de imóveis    
        """
        
        # Calcular área do polígono em hectares
        area_size_ha = self._compute_area_size_ha(geometry)

        # Carregar todos os dados necessários (evita carregar múltiplas vezes)
        # Marca o início da medição de tempo para carregamento dos dados
        _t_read_start = time.perf_counter()
        # Carrega todos os dados das bases (SICAR, Zoneamento, Fitoecologia, APAs) de uma só vez
        # O parâmetro 'car' permite ignorar um imóvel específico da base SICAR
        data_loaded = self.load_all_data_service.load_all(car=car)
        _t_read_end = time.perf_counter()
        # Exibe o tempo total gasto para leitura das bases
        print(f"Tempo para ler todas as bases: {(_t_read_end - _t_read_start):.3f}s")
        
        # Processar sobreposições para cada base de dados
        # Marca o início da medição de tempo para processamento de sobreposições
        _t_proc_start = time.perf_counter()
        # Organiza e executa o processamento de sobreposição para cada base carregada
        # Retorna um dicionário com os resultados separados por tipo de base
        results_by_base = self._organize_processors(
            geometry, 
            data_loaded
        )
        _t_proc_end = time.perf_counter()
        # Exibe o tempo total gasto para processar todas as sobreposições
        print(f"Tempo para processar todas as bases: {(_t_proc_end - _t_proc_start):.3f}s")
        #fim da logica de redução de processamento
    
        # Agregar métricas globais a partir das bases
        all_found_areas, total_not_evaluated, total_overlaps = self.result_aggregator.aggregate(
            results_by_base
        )
        
        # Resumo das quantidades por base (mantém chaves esperadas pela UI)
        summary_bases = self.result_aggregator.summary(
            data_loaded
        )

        # Montar dicionário final (mantém compatibilidade com templates atuais)
        final_result  = self.final_result_builder.build(
            results_by_base,
            all_found_areas,
            total_not_evaluated,
            total_overlaps,
            area_size_ha,
            summary_bases,
        )
        
        return final_result

    def _compute_area_size_ha(self, polygon_wkt: str) -> Optional[float]:
        """Calcula a área do polígono em hectares, com tratamento seguro de erros."""
        try:
            if polygon_wkt and str(polygon_wkt).strip():
                return calculate_area_ha(polygon_wkt)
        except Exception as e:
            print(f"Erro ao calcular a área do polígono. {e}")
            return None
        return None
    
    def _organize_processors(self, polygon_wkt: str, data: List[Dict[str, Any]]) -> None:
        """Organiza e processa os dados carregados com base nos loaders registrados.

        Parâmetros:
        - polygon_wkt: WKT do polígono analisado
        - data: Lista de dicionários contendo os dados carregados de cada loader
        """
        self.processors_all_data_service.set_processors(self.processor_registry.processors)

        return self.processors_all_data_service.process(polygon_wkt, data)
