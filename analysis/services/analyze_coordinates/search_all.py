import json
import time
from analysis.services.analyze_coordinates.overlap.final_result_builder import FinalResultBuilder
from analysis.services.analyze_coordinates.overlap.formatter_register import FormatterRegister
from analysis.services.analyze_coordinates.overlap.geometry_target import GeometryTarget
from analysis.services.analyze_coordinates.overlap.pipeline import OverlapPipeline


class SearchAll:
    """
    High-level service responsible for:
    - Preparing the geometry target (CAR or external polygon)
    - Executing the overlap pipeline
    - Building the final structured response for the UI
    - Tracking performance (timing each step)
    """

    def __init__(self):
        self.pipeline = OverlapPipeline()
        self.builder = FinalResultBuilder()
        self.formatters = FormatterRegister()

    def execute(self, geometry_or_car):
        performance = {}

        # ------------------------------------------------------
        # Detect input type and create a GeometryTarget
        # ------------------------------------------------------
        t0 = time.perf_counter()

        if hasattr(geometry_or_car, "usable_geometry"):
            target = GeometryTarget(geometry_or_car.usable_geometry)
            target.car = geometry_or_car
            input_type = "CAR"
        else:
            target = GeometryTarget(geometry_or_car)
            target.car = None
            input_type = "ExternalGeometry"

        performance["input_type"] = input_type
        performance["time_target_creation"] = time.perf_counter() - t0

        # ------------------------------------------------------
        # Run overlap pipeline
        # ------------------------------------------------------
        t1 = time.perf_counter()

        layers = list(self.formatters.formatters.keys())

        pipeline_result= self.pipeline.run(
            target=target,
            layers=layers,
            formatters=self.formatters.formatters,
        )

        performance["time_pipeline_total"] = time.perf_counter() - t1

        # ------------------------------------------------------
        # Build final structured output (UI format)
        # ------------------------------------------------------
        t2 = time.perf_counter()

        final_output = self.builder.build(
            target=target,
            results_by_layer=pipeline_result,
            layers=layers,
        )

        performance["time_builder"] = time.perf_counter() - t2

        # ------------------------------------------------------
        # Save output for debugging
        # ------------------------------------------------------
        with open("performance_log.json", "w") as f:
            json.dump(performance, f, indent=2)

        return final_output
