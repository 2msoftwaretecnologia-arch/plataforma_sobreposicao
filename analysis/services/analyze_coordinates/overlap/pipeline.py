import time
from analysis.services.analyze_coordinates.overlap.overlap_service import OverlapService


class OverlapPipeline:
    """
    Pipeline responsible for orchestrating overlap computation
    and applying formatters to each environmental layer.
    """

    def run(self, target, layers, formatters):
        print("\n===== OVERLAP PIPELINE START =====")
        pipeline_start = time.perf_counter()

        service = OverlapService(target)
        result = {}

        total_registros = 0
        total_intersecoes = 0
        total_usavel = 0
        total_sem_usavel = 0

        print("\nBases disponíveis e contagem total:")
        for layer in layers:
            count = layer.objects.count()
            total_registros += count
            print(f"  • {layer.__name__}: {count} registros")

        for layer in layers:
            layer_name = layer.__name__
            print(f"\n--- Processing layer: {layer_name} ---")

            layer_start = time.perf_counter()

            formatter = formatters.get(layer)
            if formatter is None:
                raise ValueError(f"No formatter registered for layer: {layer_name}")

            # ----------------------------------------------------------
            # 1️⃣ Compute intersections (PostGIS)
            # ----------------------------------------------------------
            t0 = time.perf_counter()
            rows = service.compute_intersections(layer)
            t1 = time.perf_counter()

            print(f"  • Time computing intersections: {t1 - t0:.4f}s "
                  f"({len(rows)} intersections found)")

            # ----------------------------------------------------------
            # 2️⃣ Format results
            # ----------------------------------------------------------
            formatted_start = time.perf_counter()
            formatted_rows = []

            for row in rows:
                # 2.1 Query object from DB
                q0 = time.perf_counter()
                obj = layer.objects.get(id=row["id"])
                q1 = time.perf_counter()

                # 2.2 Apply formatter
                f0 = time.perf_counter()
                formatted_rows.append(formatter.format(obj, row))
                f1 = time.perf_counter()

                print(f"    - Record ID {row['id']} | "
                      f"DB fetch: {q1 - q0:.4f}s | "
                      f"Formatter: {f1 - f0:.4f}s")

            formatted_end = time.perf_counter()

            print(f"  • Time formatting rows: {formatted_end - formatted_start:.4f}s")

            layer_total = layer.objects.count()
            layer_usavel = layer.objects.exclude(usable_geometry__isnull=True).count()
            layer_sem_usavel = layer_total - layer_usavel
            layer_intersecoes = len(rows)

            total_usavel += layer_usavel
            total_sem_usavel += layer_sem_usavel
            total_intersecoes += layer_intersecoes

            print(
                f"  • Resumo {layer_name}: total={layer_total}, "
                f"com_geometria_util={layer_usavel}, sem_geometria_util={layer_sem_usavel}, "
                f"intersecoes={layer_intersecoes}"
            )

            # Save results
            result[layer_name] = formatted_rows

            layer_end = time.perf_counter()
            print(f"--- Layer {layer_name} finished in {layer_end - layer_start:.4f}s ---")

        # ----------------------------------------------------------
        # END
        # ----------------------------------------------------------
        pipeline_end = time.perf_counter()
        print(f"\n===== OVERLAP PIPELINE FINISHED in {pipeline_end - pipeline_start:.4f}s =====\n")
        print(
            f"[LOG] Processamento concluído: bases={len(layers)}, registros_totais={total_registros}, "
            f"com_geometria_util={total_usavel}, sem_geometria_util={total_sem_usavel}, intersecoes_totais={total_intersecoes}"
        )

        return result
