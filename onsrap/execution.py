from __future__ import annotations

import inspect
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

from .errors import StageExecutionError, StageLoadError
from .loader import PREFERRED_ENTRYPOINTS, discover_python_entrypoint, load_python_callable
from .logger import Logger
from .models import PipelineConfig, StageResult, StageStatus, now

if TYPE_CHECKING:
    from .stage import Stage


@dataclass
class ExecutionContext:
    pipeline_name: str
    run_id: str
    config: PipelineConfig
    logger: Logger
    run_dir: Path
    started_at: datetime = field(default_factory=now)
    working_directory: Path = field(default_factory=Path.cwd)
    stage_results: dict[str, StageResult] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def record(self, result: StageResult) -> StageResult:
        self.stage_results[result.name] = result
        self.variables[result.name] = result.outputs
        return result

    def result_for(self, stage_name: str) -> StageResult | None:
        return self.stage_results.get(stage_name)

    @property
    def stage_outputs(self) -> dict[str, Any]:
        return {name: result.outputs for name, result in self.stage_results.items()}


class StageExecutor(Protocol):
    def execute(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        ...


class PythonStageExecutor:
    def __init__(self, preferred_entrypoints: tuple[str, ...] = PREFERRED_ENTRYPOINTS):
        self.preferred_entrypoints = preferred_entrypoints

    def execute(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        if callable(stage.source):
            return self._execute_callable(stage, context, stage.source, stage.source_label)

        if isinstance(stage.source, Path):
            return self._execute_file(stage, context)

        raise StageExecutionError(
            f"Stage '{stage.name}' does not have an executable source.",
            stage_name=stage.name,
            source=stage.source_label,
        )

    def _execute_callable(
        self,
        stage: "Stage",
        context: ExecutionContext,
        callable_object: Any,
        source_label: str | None,
    ) -> StageResult:
        started_at = now()
        context.logger.event(
            "Stage started",
            stage=stage.name,
            mode="callable",
            source=source_label,
        )

        try:
            output = _invoke_callable(callable_object, stage, context)
        except Exception as exc:
            finished_at = now()
            result = StageResult(
                name=stage.name,
                status=StageStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                outputs=None,
                metadata=dict(stage.metadata),
                error=str(exc),
                source=source_label,
            )
            raise StageExecutionError(
                "Callable stage failed.",
                stage_name=stage.name,
                source=source_label,
                original_exception=exc,
                result=result,
            ) from exc

        finished_at = now()
        result = _build_success_result(
            stage,
            started_at,
            finished_at,
            output,
            source=source_label,
        )
        context.logger.event(
            "Stage finished",
            stage=stage.name,
            mode="callable",
            status=result.status.value,
        )
        return result

    def _execute_file(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        path = stage.source
        assert isinstance(path, Path)

        if path.suffix.lower() == ".py":
            entrypoint = stage.entrypoint or discover_python_entrypoint(path)
            if entrypoint is not None:
                try:
                    target = load_python_callable(path, entrypoint)
                except Exception as exc:
                    failed_result = StageResult(
                        name=stage.name,
                        status=StageStatus.FAILED,
                        started_at=now(),
                        finished_at=now(),
                        outputs=None,
                        metadata=dict(stage.metadata),
                        error=str(exc),
                        source=str(path),
                    )
                    raise StageLoadError(
                        "Python stage entrypoint could not be loaded.",
                        stage_name=stage.name,
                        source=str(path),
                        original_exception=exc,
                        result=failed_result,
                    ) from exc

                return self._execute_callable(stage, context, target, str(path))

            if not context.config.allow_subprocess_fallback:
                failed_result = StageResult(
                    name=stage.name,
                    status=StageStatus.FAILED,
                    started_at=now(),
                    finished_at=now(),
                    outputs=None,
                    metadata=dict(stage.metadata),
                    error="No callable entrypoint was found in the Python file.",
                    source=str(path),
                )
                raise StageExecutionError(
                    "Python stage has no callable entrypoint and subprocess fallback is disabled.",
                    stage_name=stage.name,
                    source=str(path),
                    result=failed_result,
                )

        return self._execute_subprocess(stage, context)

    def _execute_subprocess(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        path = stage.source
        assert isinstance(path, Path)

        started_at = now()
        context.logger.event(
            "Stage started",
            stage=stage.name,
            mode="subprocess",
            source=str(path),
        )

        command = [str(path)]
        if path.suffix.lower() == ".py":
            command = [context.config.python_executable or sys.executable, str(path)]

        completed = subprocess.run(
            command,
            cwd=str(context.working_directory),
            capture_output=True,
            text=True,
            check=False,
        )

        finished_at = now()
        result = StageResult(
            name=stage.name,
            status=StageStatus.SUCCEEDED if completed.returncode == 0 else StageStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            outputs=completed.stdout,
            stdout=completed.stdout,
            stderr=completed.stderr,
            return_code=completed.returncode,
            metadata=dict(stage.metadata),
            error=None
            if completed.returncode == 0
            else completed.stderr.strip() or "Subprocess returned a non-zero exit code.",
            source=str(path),
        )

        context.logger.event(
            "Stage finished",
            stage=stage.name,
            mode="subprocess",
            status=result.status.value,
            return_code=completed.returncode,
        )

        if completed.returncode != 0:
            raise StageExecutionError(
                "Subprocess stage failed.",
                stage_name=stage.name,
                source=str(path),
                result=result,
            )

        return result


def _invoke_callable(callable_object: Any, stage: "Stage", context: ExecutionContext) -> Any:
    signature = inspect.signature(callable_object)
    parameters = list(signature.parameters.values())

    keyword_arguments: dict[str, Any] = {}
    if "context" in signature.parameters:
        keyword_arguments["context"] = context
    elif "ctx" in signature.parameters:
        keyword_arguments["ctx"] = context

    if "stage" in signature.parameters:
        keyword_arguments["stage"] = stage
    elif "task" in signature.parameters:
        keyword_arguments["task"] = stage

    if keyword_arguments:
        return callable_object(**keyword_arguments)

    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)

    if not positional_parameters and not has_varargs:
        return callable_object()

    if len(positional_parameters) == 1 and not has_varargs:
        first_name = positional_parameters[0].name.lower()
        if first_name in ("stage", "task"):
            return callable_object(stage)
        return callable_object(context)

    if len(positional_parameters) >= 2 or has_varargs:
        first_name = positional_parameters[0].name.lower() if positional_parameters else ""
        second_name = positional_parameters[1].name.lower() if len(positional_parameters) > 1 else ""
        if first_name in ("stage", "task") and second_name in ("context", "ctx"):
            return callable_object(stage, context)
        if first_name in ("context", "ctx") and second_name in ("stage", "task"):
            return callable_object(context, stage)
        return callable_object(context, stage)

    return callable_object()


def _build_success_result(
    stage: "Stage",
    started_at: datetime,
    finished_at: datetime,
    output: Any,
    *,
    source: str | None = None,
) -> StageResult:
    if isinstance(output, StageResult):
        if output.name != stage.name:
            output.name = stage.name
        if output.source is None:
            output.source = source
        if output.status == StageStatus.PENDING:
            output.status = StageStatus.SUCCEEDED
        return output

    return StageResult(
        name=stage.name,
        status=StageStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=finished_at,
        outputs=output,
        metadata=dict(stage.metadata),
        source=source,
    )