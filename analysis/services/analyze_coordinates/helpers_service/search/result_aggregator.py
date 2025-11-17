# services/search/result_aggregator.py
class ResultAggregator:
    """Responsável por consolidar métricas e dados das bases."""

    def aggregate(self, results_by_base):
        all_areas = []
        total_not_eval = 0
        total_overlaps = 0

        for base in results_by_base:
            all_areas.extend(base["areas_encontradas"])
            total_not_eval += base["quantidade_nao_avaliados"]
            total_overlaps += base["total_areas_com_sobreposicao"]

        return all_areas, total_not_eval, total_overlaps

    def summary(self, pipeline):
        return {entry["base_name"]: len(entry.get("data", [])) 
                for entry in pipeline}
