# services/search/final_result_builder.py
class FinalResultBuilder:
    """Responsável por montar o dicionário final para a UI."""

    def build(self,
              results_by_base,
              all_areas,
              total_not_eval,
              total_overlaps,
              area_size_ha,
              summary_bases):
        
        return {
            "resultados_por_base": results_by_base,
            "areas_encontradas": all_areas,
            "quantidade_nao_avaliados": total_not_eval,
            "total_areas_com_sobreposicao": total_overlaps,
            "tamanho_area": area_size_ha,
            "resumo_bases": summary_bases,
        }
