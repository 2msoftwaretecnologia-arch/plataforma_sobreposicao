from typing import Any, Dict, List
from kernel.service.geometry_overlap_service import OverlapChecker


class ProcessAllDataService:
    """
    Serviço para processar dados de várias bases de forma consolidada.
    """
    def __init__(self):
        self._processors_map: Dict[Any, Any] = {}

    def set_processors(self, processors_map: Dict[Any, Any]) -> None:
        self._processors_map = processors_map

    def process(self, polygon_wkt: str, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results_by_base: List[Dict[str, Any]] = []

        for entry in pipeline:
            loader_cls = entry.get("loader")
            processor = self._processors_map.get(loader_cls)
            if not processor:
                continue
            base_name = entry.get("base_name")
            data = entry.get("data")
            result = processor.process(polygon_wkt, data, base_name)
            results_by_base.append(result)

        return results_by_base
