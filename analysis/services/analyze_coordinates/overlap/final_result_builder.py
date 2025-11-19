class FinalResultBuilder:

    def build(self, target, results_by_layer, layers):
        """
        Build the final structured response for the UI in the expected format.

        Parameters:
        - target: GeometryTarget (may contain .car reference)
        - results_by_layer: dict { "LayerName": [ {...}, {...} ] }
        - layers: list of Django model classes

        Returns:
        A JSON-ready dict.
        """

        bases_output = []
        all_areas = []

        for layer in layers:
            layer_name = layer.__name__
            records = results_by_layer.get(layer_name, [])

            bases_output.append({
                "nome_base": self._base_name(layer),
                "areas_encontradas": records,
                "quantidade_nao_avaliados": 0,
                "total_areas_com_sobreposicao": len(records),
            })

            all_areas.extend(records)

        summary_counts = {
            self._base_name(layer): layer.objects.count()
            for layer in layers
        }

        return {
            "resultados_por_base": bases_output,
            "areas_encontradas": all_areas,
            "quantidade_nao_avaliados": 0,
            "total_areas_com_sobreposicao": len(all_areas),
            "tamanho_area": target.area_ha,   # works for CAR and external polygon
            "resumo_bases": summary_counts,
        }

    def _base_name(self, layer):
        mapping = {
            "SicarRecord": "Base de Dados Sicar",
            "ZoningArea": "Base de Dados de Zoneamento",
            "PhytoecologyArea": "Base de Dados de Fitoecologias",
            "EnvironmentalProtectionArea": "Base de Dados de APAs",
            "IndigenousArea": "Base de Dados de Indígenas",
        }
        return mapping.get(layer.__name__, layer.__name__)
