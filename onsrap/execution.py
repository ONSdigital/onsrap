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
    """
    Holds information needed to run the pipeline.

    Parameters 
    ----------
    ``pipeline_name`` : str
        The name of the pipeline.
    ``run_id`` : str
        The unique identifier for the current run of the pipeline.
    ``config`` : ``PipelineConfig`` class instance
        The configuration required for the pipeline.
    ``logger`` : ``Logger`` class instance
        The logger used for this pipeline run.
    ``run_dir``: Path
        The directory that the run saved to.
    ``started_at`` : datetime, default = current time
        The time that the pipeline run started.
    ``working_directory`` : Path, default = current working directory
        The directory that the work is taking place in.
    ``stage_results`` : dict[str, StageResult], default = dict
        Stores the logs for the stage run.
    ``variables`` : dict[str, Any], default = dict
        Stores relevant variables regarding the stage run and their results.
    """
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
        """
        Extracts key information from ``StageResult``.

        Saves all information on the results of the Stage to the ``stage_results`` attribute
        and exclusively metadata outputs regarding the run to the ``variables`` attribute.

        Parameters 
        ----------
        ``result`` : ``StageResult``
            An instance of a ``StageResult`` class which is created from the Executor classes (StageExecutor, PythonStageExecutor).

        Returns
        ------
        ``result``
            An unchanged ``StageResult`` instance.
        """ 
        self.stage_results[result.name] = result
        self.variables[result.name] = result.outputs
        return result

    def result_for(self, stage_name: str) -> StageResult | None:
        """
        Getter function that returns the stage_results for a specific ``Stage``.

        Parameters
        ----------
        ``stage_name`` : str
            The name of the ``Stage`` that you are calling the results for.

        Returns 
        -------
        ``stage_results`` 
            Attribute for the specific `Stage` named.
        """
        return self.stage_results.get(stage_name)

    @property
    def stage_outputs(self) -> dict[str, Any]:
        """
        Creates a ``stage_outputs`` attribute for the ``ExecutionContext`` class. 

        Extracts the ```outputs`` attribute from the ``stage_results`` class for each
        ``Stage`` name.

        Returns 
        ------- 
        ``stage_outputs``
            Dictionary containing the name of the stage and the associated outputs of 
            the run.
        """
        return {name: result.outputs for name, result in self.stage_results.items()}


class StageExecutor(Protocol):
    """
    Child class of ``Protocol`` 
    Implementation required
    """
    def execute(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        """
        Method to run ``Stage`` however implementation required
        """
        ...


class PythonStageExecutor:
    """
    Class to run Python `Stage`.

    Contains methods that allow automatic running of individual `Stage` processes for
    a pipeline. 
    """
    def __init__(self, preferred_entrypoints: tuple[str, ...] = PREFERRED_ENTRYPOINTS):
        self.preferred_entrypoints = preferred_entrypoints

    def execute(self, stage: "Stage", context: ExecutionContext) -> StageResult:
        """
        Main function to select how ``Stage`` is run.

        Identifies the type of ``source`` within the ``Stage`` and runs the relevant 
        function for that type.

        Parameters
        ----------
        ``stage`` : ``Stage`` class
            The ``Stage`` that is attempting to be run.

        ``context`` : ``ExecutionContext`` class
            The metadata required to run the ``Stage``.

        Return
        ------
        ``StageResult`` instance.

        Raise
        -----
        ``StageExecutionError``
            If the ``source`` is not a Path or a callable object. 
        """
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
        """
        Attempt to run a callable object.

        Calls the logger.event() method to record an event and attempts to 
        run the callable parsed. If the callable cannot be run, an error is flagged 
        and the ``StageResult`` instance created shows a failure. If it can be run, 
        the callable is run and the ``StageResult`` instance shows a success. 
        Metadata is kept for the attempt including ``duration``, ``name``, ``outputs``, 
        ``source``, ``mode`` attempted, and ``errors``.

        Parameters
        ----------
        ``stage`` : ``Stage`` class
            A ``Stage`` class instance for the stage being run.
        ``context`` : ``ExecutionContext`` class
            The metadata required to run the ``Stage``.
        ``callable_object`` : Any
            The callable attempting to be run.
        ``source_label`` : str or None
            The type of ``source`` for the ``Stage``.

        Return
        ------
        ``StageResult`` class instance

        Raise
        -----
        ``StageExecutionError``
            If the callable object cannot be run
        """
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
        """
        Attempt to run a file.

        """
        Attempt to run a callable object.

        Calls the logger.event() method to record an event and attempts to run 
        the callable parsed. If the callable cannot be run, an error is flagged and 
        the ``StageResult`` instance created shows a failure. If it can be run, the 
        callable is run and the ``StageResult`` instance shows a success. Metadata 
        is kept for the attempt including ``duration``, ``name``, ``outputs``, ``source``,
         ``mode`` attempted, and ``errors``.
        If there is no entrypoint or the entrypoint is not a callable object, an error will be 
        raised. ``_execute_subprocess()`` method called if no entrypoint is found. A 
        ``StageResult`` instance will be created to log the results of the ``Stage``run regardless 
        of success or failure.

        Parameters
        ----------
        ``stage`` : ``Stage`` class
            A ``Stage`` class instance for the stage being run.
        ``context`` : ``ExecutionContext`` class
            The metadata required to run the ``Stage``.

        Return
        ------
        ``StageResult`` class instance

        Raise
        -----
        ``StageLoadError``
            If the entrypoint in the stage is unable to be run.
        ``StageExecutionError``
            If the entrypoint is not found.
        """
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
        """
        Run the entire Python file for the ``Stage`` from the top.
        
        Not desired method. Uses black-box design and obfuscates Pipeline running. Please refer 
        to Wiki documentation on how to implement callable solutions instead.

        If the ``Stage`` source is a file but does not have a callable entrypoint, this method
        will run the entire script top to bottom. The results of the ``Stage`` are recorded
        as a ``StageResult`` instance and logging processes are complete.

        Parameters
        ----------
        ``stage`` : ``Stage`` class
            A ``Stage`` class instance for the stage being run.
        ``context`` : ``ExecutionContext`` class
            The metadata required to run the ``Stage``.
        
        Return
        ------
        ``result``
            A ``StageResult`` instance holding information on the ``Stage``.

        Raise
        -----
        ``StageExecutionError``
            If the ``Stage`` script was unable to be run successfully.
        """
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
    """
    Assigns appropriate parameters for a callable and runs it. 

    Searches for parameter terms that likely refer to context or stage. If none of these are found, 
    assigns ``context`` as the first parameter and ``stage`` as the second.  

    Parameters
    ----------
    ``callable_object`` : Any 
        The callable item that is going to be run. 
    ``stage`` : ``Stage`` class 
        The ``Stage`` class instance to be a parameter for the ``callable_object``. 
    ``context`` : ``ExecutionContext`` class
        The ``ExecutionContext`` class instance to be a parameter for the ``callable_object``. 
    
    Returns
    -------
    ``callable_object``
        An invocation of the ``callable_object`` with appropriately assigned parameters.
    """
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
    """
    Create a ``StageResult`` instance showing a successful stage run.

    If the output of a ``Stage`` run is a ``StageResult`` class, set missing attributes to relevant
    information from the ``Stage``. 

    Parameters
    ----------
    ``stage`` : ``Stage`` class
        The ``Stage`` class instance being run.
    ``started_at`` : datetime
        The time and date that the run started. 
    ``finished_at`` : datetime
        The time and date that the run ended.
    ``output`` : Any
        The output produced from the stage run.
    ``source`` : str or None
        The file/callable being run in the stage.
        
    Return
    ------
    ``StageResult`` instance
        Containing metadata for the stage run and showing that the run was a success. 
    """
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