from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import StageExecutionError
from .warnings import StageConfigurationWarning
from .execution import ExecutionContext
from .logger import Logger
from .models import PipelineRun, PipelineStatus, RunManifest, now

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

        def __str__(self) -> str:
            """
            String method that returns a human-readable representation of the ``PipelineRunner`` class.

            Returns
            -------
            str
                A string representation of the ``PipelineRunner`` class with its attributes.
            """
            return (
                f"PipelineRunner Instance Attributes\n"
                f"--------------------------\n"
                f"Logger: {self.logger} \n"
            )

        def __repr__(self) -> str:
            """
            Representation method that returns a human readable representation of the ``PipelineRunner`` class. 
            This method is structured to be more concise than the ``__str__`` method and is 
            intended for debugging purposes.

            Returns 
            -------
            str
                A string representation of the ``PipelineRunner`` class with its attributes.
            """
            return (
                f"PipelineRunner(logger={self.logger})"
            )

    def run(self, pipeline: Pipeline) -> PipelineRun:
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
        # Initial Pipeline steps - validate, create run ID and any relevant directories.
        pipeline.validate()

        runtime_id = pipeline._create_runtime_id()
        pipeline.id = runtime_id

        if pipeline.config.output_dir is not None:
            run_output = Path(pipeline.config.output_dir)
        else:
            warnings.warn(
                "Output directory is not specified. Using project root or work directory as the run output.",
                StageConfigurationWarning
            )  # TODO: fill with warnings from Pipeline branch
            run_output = Path(pipeline.config.project_root or pipeline.config.work_dir)
        run_dir = run_output / "runs" / runtime_id.get_id()
        run_dir.mkdir(parents=True, exist_ok=True)

        # Initialise the ExecutionContext which will be passed to each stage as it runs. This
        # context will hold the configuration for the pipeline and for each stage.
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
            global_config=pipeline.global_config,
        )

        # Ensure the stages are in order and create a manifest that explains the run.

        ordered_stages = pipeline.ordered_stages()
        manifest = pipeline._construct_manifest(runtime_id=runtime_id)
        manifest.stages_run = []
        manifest.outputs = {}
        pipeline.manifest = manifest

        _log_config(run_dir, context, manifest)

        self.logger.event(
            "Pipeline started",
            name=pipeline.name,
            run_id=runtime_id.get_id(),
            stages=[stage.name for stage in ordered_stages],
        )

        # Execution of the stages in the dependency-driven order.
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
            # Handle recording of execution errors.
            if exc.result is not None and context.result_for(exc.result.name) is None:
                context.record(exc.result)
                stage_results.append(exc.result)
                manifest.stages_run.append(exc.result.name)
                manifest.outputs[exc.result.name] = exc.result.outputs

            # Log the failure and raise the exception to indicate the pipeline has failed.
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

        # If the pipeline has completed successfully, record the completion and return the run information.
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


def _log_config(run_dir: str, context: ExecutionContext, manifest: RunManifest) -> None:
    """
    Outputs the configurations used in an instance of a pipeline to a YAML file in the run directory. 

    The file is kept in the block flow style typically expected of a YAML file. 

    Parameters
    ----------
    ``run_dir`` : str
        The directory where the pipeline run is being executed. 
    ``context`` : ExecutionContext
        The context of the current pipeline run, containing configuration and state information.
    ``manifest`` : RunManifest
        The manifest of the current pipeline run, containing metadata and outputs.
    """
    config_file = Path(run_dir) / f"configuration_for_{context.pipeline_name}_{context.started_at}_{context.run_id}.yaml"
    import yaml
    with open(config_file, "w") as f:
        yaml.safe_dump(manifest.config, f, default_flow_style=False)

