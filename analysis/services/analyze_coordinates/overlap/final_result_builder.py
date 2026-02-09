from django.contrib.gis.geos import GEOSGeometry

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
            original_records = results_by_layer.get(layer_name, [])

            grouped_records = self._group_records(layer_name, original_records)

            # Ordena os registros da maior área para a menor
            grouped_records.sort(key=lambda x: float(x.get("area") or 0), reverse=True)

            base_entry = self._build_base_entry(layer, grouped_records)
            bases_output.append(base_entry)

            all_areas.extend(grouped_records)

            for r in original_records:
                r["color"] = self._base_color(layer)
                wkt = r.get("polygon_wkt")
                gj = r.get("polygon_geojson")
                if isinstance(gj, str) and gj.strip().startswith("{"):
                    property_polygons.append({
                        "fonte": self._base_name(layer),
                        "item_info": r.get("item_info"),
                        "area": r.get("area"),
                        "polygon_wkt": wkt,
                        "polygon_geojson": gj,
                        "color": self._base_color(layer),
                    })

        # Ordena as bases para exibir primeiro aquelas com maior área total sobreposta
        bases_output.sort(
            key=lambda b: sum(float(r.get("area") or 0) for r in b.get("areas_encontradas", [])),
            reverse=True
        )

        summary_counts = self._build_summary_counts(layers)

        tg = getattr(target, "geometry", None)
        alvo_geojson = getattr(tg, "geojson", None) if tg else None
        alvo_wkt = tg.wkt if tg else None
        
        data = {
            "resultados_por_base": bases_output,
            "areas_encontradas": all_areas,
            "quantidade_nao_avaliados": 0,
            "total_areas_com_sobreposicao": len(all_areas),
            "area_preservada_total": self._get_fitoecologia_preserved_area(bases_output),
            "tamanho_area": target.area_ha,
            "resumo_bases": summary_counts,
            "poligonos_imoveis": property_polygons,
            "alvo_geojson": alvo_geojson,
            "alvo_wkt": alvo_wkt,
        }
        
        return data

    def _get_fitoecologia_preserved_area(self, bases_output):
        for base in bases_output:
            if base.get("nome_base") == "Base de Dados de Fitoecologias":
                return base.get("total_preserved_area", 0)
        return 0

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
                # Inicializa com a geometria atual
                geom = None
                if r.get("polygon_wkt"):
                    try:
                        geom = GEOSGeometry(r.get("polygon_wkt"))
                    except:
                        pass

                grouped[key] = {
                    "nome": key,
                    "area": r.get("area", 0) or 0,
                    "item_info": key,
                    "preserved_area": r.get("preserved_area", 0),
                    "_geom_obj": geom # Armazena objeto temporário para união
                }
            else:
                acc["area"] = (acc.get("area", 0) or 0) + (r.get("area", 0) or 0)
                acc["preserved_area"] = (acc.get("preserved_area", 0) or 0) + (r.get("preserved_area", 0) or 0)
                
                # Une geometria
                if r.get("polygon_wkt"):
                    try:
                        new_geom = GEOSGeometry(r.get("polygon_wkt"))
                        if acc["_geom_obj"]:
                            acc["_geom_obj"] = acc["_geom_obj"].union(new_geom)
                        else:
                            acc["_geom_obj"] = new_geom
                    except:
                        pass
        
        # print(grouped)
        
        # Finaliza processamento (converte geom para string)
        results = []
        for val in grouped.values():
            geom = val.pop("_geom_obj", None)
            if geom:
                val["polygon_wkt"] = geom.wkt
                val["polygon_geojson"] = geom.geojson
            results.append(val)

        return results

    def _build_base_entry(self, layer, records):
        """
        Cria o dicionário de saída para uma base específica.

        Inclui nome da base, itens encontrados e contagem de sobreposições.
        """
        total_area = sum(float(r.get("area") or 0) for r in records)
        data = {
            "nome_base": self._base_name(layer),
            "areas_encontradas": records,
            "quantidade_nao_avaliados": 0,
            "total_areas_com_sobreposicao": len(records),
            "total_area": total_area,
        }

        if layer.__name__ == "PhytoecologyArea":
            data["total_preserved_area"] = sum(float(r.get("preserved_area") or 0) for r in records)

        return data

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
            "Embargoes": "Base de Embargos do IBAMA",
            "Ipuca": "Base de Dados IPUCA",
        }
        return mapping.get(layer.__name__, layer.__name__)

    def _base_color(self, layer):
        mapping = {
            "SicarRecord": "#efff00",
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
            "DeforestationMapbiomas": "#FF0000",
            "Embargoes": "#FF5722",
            "Ipuca": "#673AB7",
        }
        return mapping.get(layer.__name__, "#9E9E9E")
