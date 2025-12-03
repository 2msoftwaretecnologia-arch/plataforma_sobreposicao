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
        """
        Executa o fluxo completo de análise de sobreposição
        e retorna um dicionário pronto para uso na UI.
        """

        performance = {}

        # 1) Preparar alvo e tipo de entrada
        t0 = time.perf_counter()
        target, input_type = self._create_target_and_type(geometry_or_car)
        performance["input_type"] = input_type
        performance["time_target_creation"] = time.perf_counter() - t0

        # 2) Executar pipeline de sobreposição nas camadas
        t1 = time.perf_counter()
        layers = self._get_layers()
        pipeline_result = self._run_pipeline(target, layers)
        performance["time_pipeline_total"] = time.perf_counter() - t1

        # 3) Construir saída final estruturada
        t2 = time.perf_counter()
        final_output = self._build_final_output(target, pipeline_result, layers)
        performance["time_builder"] = time.perf_counter() - t2

        # 4) Medir tempo total e anexar à saída
        total_seconds = time.perf_counter() - t0
        performance["time_total"] = total_seconds
        self._attach_timing_to_output(final_output, performance, total_seconds)

        # 5) Persistir log de performance para depuração
        self._save_performance_log(performance)

        return final_output

    def _create_target_and_type(self, geometry_or_car):
        """
        Cria e retorna o `GeometryTarget` a partir do input.
        Também devolve o tipo de entrada ("CAR" ou "ExternalGeometry").
        """
        if hasattr(geometry_or_car, "usable_geometry"):
            target = GeometryTarget(geometry_or_car.usable_geometry)
            target.car = geometry_or_car
            return target, "CAR"
        target = GeometryTarget(geometry_or_car)
        target.car = None
        return target, "ExternalGeometry"

    def _get_layers(self):
        """
        Obtém a lista de modelos-camada que serão avaliados.
        """
        return list(self.formatters.formatters.keys())

    def _run_pipeline(self, target, layers):
        """
        Executa o pipeline de sobreposição e retorna o mapa de resultados por camada.
        """
        return self.pipeline.run(
            target=target,
            layers=layers,
            formatters=self.formatters.formatters,
        )

    def _build_final_output(self, target, pipeline_result, layers):
        """
        Constrói a saída final agregada para consumo pela interface.
        """
        return self.builder.build(
            target=target,
            results_by_layer=pipeline_result,
            layers=layers,
        )

    def _format_seconds(self, s):
        """
        Formata segundos em uma string amigável (ms, s, m s).
        """
        if s < 1:
            return f"{int(s * 1000)} ms"
        if s < 60:
            return f"{s:.2f} s"
        m = int(s // 60)
        sec = s % 60
        return f"{m}m {sec:.1f}s"

    def _attach_timing_to_output(self, final_output, performance, total_seconds):
        """
        Anexa métricas de tempo ao dicionário final emitido para a UI.
        """
        final_output["tempo_execucao_segundos"] = total_seconds
        final_output["tempo_execucao_formatado"] = self._format_seconds(total_seconds)
        final_output["performance"] = performance

    def _save_performance_log(self, performance):
        """
        Persiste o log de performance em disco para depuração.
        """
        with open("performance_log.json", "w") as f:
            json.dump(performance, f, indent=2)
