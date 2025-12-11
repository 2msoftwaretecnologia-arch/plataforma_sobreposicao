import json 

class FinalResultBuilder:

    def build(self, target, results_by_layer, layers):
        """
        Constrói o dicionário final com os resultados da análise para a UI.

        - Normaliza e agrupa registros por camada quando necessário.
        - Monta a lista de bases com contagens e áreas encontradas.
        - Calcula o resumo de quantidade de registros por base.
        """

        bases_output = []
        all_areas = []
        property_polygons = []

        for layer in layers:
            layer_name = layer.__name__
            records = results_by_layer.get(layer_name, [])

            # Agrupar registros quando aplicável (ex.: Fitoecologia)
            records = self._group_records(layer_name, records)

            # Construir entrada da base
            base_entry = self._build_base_entry(layer, records)
            bases_output.append(base_entry)

            # Acumular todas as áreas para somatório global
            all_areas.extend(records)

            # Coletar polígonos dos imóveis
            for r in records:
                r["color"] = self._base_color(layer)
                wkt = r.get("polygon_wkt")
                gj = r.get("polygon_geojson")
                if isinstance(gj, str) and gj.strip().startswith("{"):
                    property_polygons.append({
                        "fonte": self._base_name(layer),
                        "item_info": r.get("item_info"),
                        "polygon_wkt": wkt,
                        "polygon_geojson": gj,
                        "color": self._base_color(layer),
                    })

        summary_counts = self._build_summary_counts(layers)

        data = {
            "resultados_por_base": bases_output,
            "areas_encontradas": all_areas,
            "quantidade_nao_avaliados": 0,
            "total_areas_com_sobreposicao": len(all_areas),
            "tamanho_area": target.area_ha,
            "resumo_bases": summary_counts,
            "poligonos_imoveis": property_polygons,
        }

        salve = 'saida.json'

        with open(salve, 'w') as f:
            json.dump(data, f, indent=4)

        return data

    def _group_records(self, layer_name, records):
        """
        Aplica regras de agrupamento específicas por camada.

        - Para "PhytoecologyArea": agrupa por nome somando a área.
        - Para demais camadas: retorna os registros como estão.
        """
        if layer_name != "PhytoecologyArea" or not records:
            return records

        grouped = {}
        for r in records:
            key = r.get("nome")
            if key is None:
                continue
            acc = grouped.get(key)
            if acc is None:
                grouped[key] = {
                    "nome": key,
                    "area": r.get("area", 0) or 0,
                    "item_info": "Regioões FitoEcologicas: {}".format(key),
                }
            else:
                acc["area"] = (acc.get("area", 0) or 0) + (r.get("area", 0) or 0)

        return list(grouped.values())

    def _build_base_entry(self, layer, records):
        """
        Cria o dicionário de saída para uma base específica.

        Inclui nome da base, itens encontrados e contagem de sobreposições.
        """
        return {
            "nome_base": self._base_name(layer),
            "areas_encontradas": records,
            "quantidade_nao_avaliados": 0,
            "total_areas_com_sobreposicao": len(records),
        }

    def _build_summary_counts(self, layers):
        """
        Calcula o resumo de quantidade total de registros disponíveis por base.
        """
        return {
            self._base_name(layer): layer.objects.count()
            for layer in layers
        }

    def _base_name(self, layer):
        """
        Mapeia o nome técnico do modelo para o nome amigável exibido na UI.
        """
        mapping = {
            "SicarRecord": "Base de Dados Sicar",
            "ZoningArea": "Base de Dados de Zoneamento",
            "PhytoecologyArea": "Base de Dados de Fitoecologias",
            "EnvironmentalProtectionArea": "Base de Dados de APAs",
            "IndigenousArea": "Base de Dados de Indígenas",
            "Quilombolas": "Base de Dados de Quilombolas",
            "Paths": "Base de Dados de Veredas",
            "ConservationUnits": "Base de Dados de Unidades de Conservação",
            "MunicipalBoundaries": "Base de Dados de Municípios",
            "Sigef": "Base de Dados Sigef",
            "Ruralsettlement": "Base de Dados de Assentamentos Rurais",
            "SnicTotal": "Base de Dados SNIC Total",
            "DeforestationMapbiomas": "Base de Deforestação Mapbiomas",
        }
        return mapping.get(layer.__name__, layer.__name__)

    def _base_color(self, layer):
        mapping = {
            "SicarRecord": "#2E7D32",
            "ZoningArea": "#F57C00",
            "PhytoecologyArea": "#6A1B9A",
            "EnvironmentalProtectionArea": "#C62828",
            "IndigenousArea": "#8E24AA",
            "Quilombolas": "#5D4037",
            "Paths": "#00897B",
            "ConservationUnits": "#388E3C",
            "MunicipalBoundaries": "#1976D2",
            "Sigef": "#D81B60",
            "Ruralsettlement": "#00ACC1",
            "SnicTotal": "#EF6C00",
            "DeforestationMapbiomas": "#4E342E",
        }
        return mapping.get(layer.__name__, "#9E9E9E")
