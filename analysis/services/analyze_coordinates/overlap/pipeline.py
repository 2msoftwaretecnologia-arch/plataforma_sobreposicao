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

            # Save results
            result[layer_name] = formatted_rows

            layer_end = time.perf_counter()
            print(f"--- Layer {layer_name} finished in {layer_end - layer_start:.4f}s ---")

        # ----------------------------------------------------------
        # END
        # ----------------------------------------------------------
        pipeline_end = time.perf_counter()
        print(f"\n===== OVERLAP PIPELINE FINISHED in {pipeline_end - pipeline_start:.4f}s =====\n")

        return result
