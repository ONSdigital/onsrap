from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import StageExecutionError
from .execution import ExecutionContext
from .logger import Logger
from .models import PipelineRun, PipelineStatus, now

if TYPE_CHECKING:
    from .pipeline import Pipeline


class PipelineRunner:
    def __init__(self, logger: Logger | None = None):
        self.logger = logger or Logger()

    def run(self, pipeline: "Pipeline") -> PipelineRun:
        pipeline.validate()

        runtime_id = pipeline._create_runtime_id()
        pipeline.id = runtime_id

        project_root = Path(pipeline.config.project_root or pipeline.config.work_dir)
        run_dir = project_root / "runs" / runtime_id.get_id()
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
                result = stage.run(context, pipeline.executor)
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
    parser = argparse.ArgumentParser(description="Run an onsrap pipeline from Python files.")
    parser.add_argument("stages", nargs="+", help="One or more Python stage files to run.")
    parser.add_argument("--name", default=None, help="Optional pipeline name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .pipeline import Pipeline

    args = build_parser().parse_args(argv)
    pipeline = Pipeline.from_files(args.stages, name=args.name)
    pipeline.run()
    return 0
