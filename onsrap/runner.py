from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import StageExecutionError
from .execution import ExecutionContext
from .logger import Logger
from .models import PipelineRun, PipelineStatus, now

if TYPE_CHECKING:
    from .pipeline import Pipeline


class PipelineRunner:
    """
    Represents the information required to run the Pipeline. 

    Parameters
    ----------
    ``logger`` : Logger class type
        Information used to log progress throughout the Pipeline. 
    """
    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Logger()

    def run(self, pipeline: "Pipeline") -> PipelineRun:
        """
        Method that runs a ``Pipeline`` instance. 

        This method validates the source information, establishes the directories and 
        the context to run the pipeline within, sets out the manifest for the run, attempts
        to run the stages in the order outlined by the ``StageGraph`` instance and logs all
        progress alongside relevant statuses. Before each stage executes, the runner binds
        the current stage name onto the ``ExecutionContext`` so ``context.stage_config``
        resolves to the correct stage-specific configuration.

        It returns a PipelineRun instance containing metadata and logging information for the 
        specific run of the whole Pipeline. 

        Parameters
        ----------
        ``pipeline`` : Pipeline
            A Pipeline instance that this method will run. 

        Raises
        ------
        ``StageExecutionError``
            If the stage is unable to be run. Logs will be created to show a failed stage. 
        """
        pipeline.validate()

        runtime_id = pipeline._create_runtime_id()
        pipeline.id = runtime_id

        if pipeline.config.output_dir is not None:
            run_output = Path(pipeline.config.output_dir)
        else:
            warnings.warn(
                "Output directory is not specified. Using project root or work directory as the run output."
            )  # TODO: fill with warnings from Pipeline branch
            run_output = Path(pipeline.config.project_root or pipeline.config.work_dir)
        run_dir = run_output / "runs" / runtime_id.get_id()
        run_dir.mkdir(parents=True, exist_ok=True)

        started_at = now()
        context = ExecutionContext(
            pipeline_name=pipeline.name,
            run_id=runtime_id.get_id(),
            config=pipeline.config,
            logger=self.logger,
            run_dir=run_dir,
            started_at=started_at,
            working_directory=pipeline.config.work_dir,
            stage_configs=dict(pipeline.stage_configs),
        )

        ordered_stages = pipeline.ordered_stages()
        manifest = pipeline._construct_manifest(runtime_id=runtime_id)
        manifest.stages_run = []
        manifest.outputs = {}
        pipeline.manifest = manifest

        self.logger.event(
            "Pipeline started",
            name=pipeline.name,
            run_id=runtime_id.get_id(),
            stages=[stage.name for stage in ordered_stages],
        )

        stage_results = []
        try:
            for stage in ordered_stages:
                self.logger.event("Executing stage", name=stage.name, source=stage.source_label)
                context.set_active_stage(stage.name)
                try:
                    result = stage.run(context, pipeline.executor)
                finally:
                    context.set_active_stage(None)
                context.record(result)
                stage_results.append(result)
                manifest.stages_run.append(result.name)
                manifest.outputs[result.name] = result.outputs
        except StageExecutionError as exc:
            if exc.result is not None and context.result_for(exc.result.name) is None:
                context.record(exc.result)
                stage_results.append(exc.result)
                manifest.stages_run.append(exc.result.name)
                manifest.outputs[exc.result.name] = exc.result.outputs

            completed_at = now()
            run = PipelineRun(
                manifest=manifest,
                status=PipelineStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                stage_results=stage_results,
                stage_outputs=context.stage_outputs,
            )
            pipeline.manifest = manifest
            pipeline.last_run = run
            self.logger.event(
                "Pipeline failed",
                name=pipeline.name,
                run_id=runtime_id.get_id(),
                error=str(exc),
            )
            raise

        completed_at = now()
        run = PipelineRun(
            manifest=manifest,
            status=PipelineStatus.SUCCEEDED,
            started_at=started_at,
            completed_at=completed_at,
            stage_results=stage_results,
            stage_outputs=context.stage_outputs,
        )
        pipeline.manifest = manifest
        pipeline.last_run = run

        self.logger.event(
            "Pipeline completed",
            name=pipeline.name,
            run_id=runtime_id.get_id(),
            stages=len(stage_results),
        )
        return run


def build_parser() -> argparse.ArgumentParser:
    """
    Determines what arguments are needed when running a Pipeline from the command line. 

    Enables stages to be input, followed by a name if provided. 
    """
    parser = argparse.ArgumentParser(description="Run an onsrap pipeline from Python files.")
    parser.add_argument("stages", nargs="+", help="One or more Python stage files to run.")
    parser.add_argument("--name", default=None, help="Optional pipeline name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Entrypoint to the pipeline. 

    This function can be called from the command line. It builds a parser which enables
    the arguments to be held before using those arguments to build a Pipeline instance.
    The pipeline.run() method is then run which runs the entire pipeline. If this runs 
    successfully, a 0 is returned which is the success code. 

    Parameters
    ----------
    ``argv`` : list[str] or None
        Command line arguments to parse. 
    
    Returns
    -------
    int 
        Success code for completion of the run. 
    """
    from .pipeline import Pipeline

    args = build_parser().parse_args(argv)
    pipeline = Pipeline.from_files(args.stages, name=args.name)
    pipeline.run()
    return 0
