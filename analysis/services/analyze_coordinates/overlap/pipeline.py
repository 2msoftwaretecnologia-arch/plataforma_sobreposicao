from analysis.services.analyze_coordinates.overlap.overlap_service import OverlapService


class OverlapPipeline:
    """
    Pipeline responsible for orchestrating overlap computation
    and applying formatters to each environmental layer.
    """

    def run(self, target, layers, formatters):
        service = OverlapService(target)
        result = {}

        for layer in layers:
            layer_name = layer.__name__

            formatter = formatters.get(layer)
            if formatter is None:
                raise ValueError(f"No formatter registered for layer: {layer_name}")

            rows = service.compute_intersections(layer)

            # O objeto já vem carregado em `row["instance"]` (calculado durante
            # a intersecção no banco) — evita um SELECT extra por resultado.
            result[layer_name] = [
                formatter.format(row["instance"], row) for row in rows
            ]

        return result
