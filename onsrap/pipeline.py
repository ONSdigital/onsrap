from __future__ import annotations

import getpass
import hashlib
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import StageConfigurationError
from .execution import PythonStageExecutor, StageExecutor
from .graph import StageGraph
from .logger import Logger
from .models import PipelineConfig, PipelineRun, RAPConfig, RunManifest, RuntimeID, now
from .stage import Stage


class Pipeline:
    def __init__(
        self,
        name: str | None = None,
        backend: str = "python",
        config: PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None = None,
        stages: Sequence[Stage | Mapping[str, Any] | str | Path | Callable[..., Any]] | None = None,
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ):
        self.name = name or "pipeline"
        self.backend = backend or "python"
        self.config = PipelineConfig.from_any(config)
        if self.config.name is None:
            self.config.name = self.name
        self.config.backend = self.backend

        self.logger = logger or Logger(log_dir=self.config.log_dir)
        self.executor = executor or PythonStageExecutor()
        self.stages = [self._coerce_stage(stage) for stage in (stages or [])]
        self.graph = StageGraph.from_stages(self.stages)
        self.id: RuntimeID | None = None
        self.manifest: RunManifest | None = None
        self.last_run: PipelineRun | None = None

        self.logger.event(
            "Pipeline initialized",
            name=self.name,
            backend=self.backend,
            stages=[stage.name for stage in self.stages],
        )

    def _coerce_stage(
        self,
        stage: Stage | Mapping[str, Any] | str | Path | Callable[..., Any],
    ) -> Stage:
        if isinstance(stage, Stage):
            return stage

        if isinstance(stage, Mapping):
            return Stage.from_dict(stage)

        if callable(stage):
            return Stage.from_callable(stage)

        if isinstance(stage, (str, Path)):
            return Stage.from_file(stage)

        raise StageConfigurationError(f"Unsupported stage specification: {type(stage)!r}.")

    def _rebuild_graph(self) -> None:
        self.graph = StageGraph.from_stages(self.stages)

    def add_stage(self, *stages: Stage | Mapping[str, Any] | str | Path | Callable[..., Any]) -> None:
        added_stages = [self._coerce_stage(stage) for stage in stages]
        self.stages.extend(added_stages)
        self._rebuild_graph()
        self.logger.event("Stage added", stages=[stage.name for stage in added_stages])

    def ordered_stages(self) -> list[Stage]:
        return self.graph.topological_order()

    def validate(self) -> "Pipeline":
        self.logger.event("Validating pipeline", name=self.name)
        for stage in self.stages:
            stage.validate()
        self.graph.validate()
        return self

    def run(self) -> PipelineRun:
        from .runner import PipelineRunner

        return PipelineRunner(logger=self.logger).run(self)

    def _construct_manifest(self, *, runtime_id: RuntimeID) -> RunManifest:
        return RunManifest(
            rap_name=self.name,
            run_id=runtime_id.get_id(),
            git_commit=self._discover_git_commit(),
            stages_run=[],
            parameters=self.config.to_dict(),
            inputs={stage.name: list(stage.dependencies) for stage in self.stages},
            outputs={},
            backend=self.backend,
            package_versions=self._package_versions(),
            timestamp=runtime_id.timestamp.isoformat(),
            reason=self.config.metadata.get("reason"),
            user=self._current_user(),
        )

    def _create_runtime_id(self) -> RuntimeID:
        current_time = now()
        digest = hashlib.sha256(f"{self.name}:{self.backend}:{current_time.isoformat()}".encode("utf-8")).hexdigest()
        short_hash = digest[:8]
        return RuntimeID(
            id=f"{current_time.strftime('%Y-%m-%d_%H%M%S')}_{short_hash}",
            timestamp=current_time,
            hash=digest,
            short_hash=short_hash,
        )

    def _discover_git_commit(self) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None

        commit = completed.stdout.strip()
        return commit or None

    def _package_versions(self) -> list[str]:
        versions = [f"python={sys.version.split()[0]}"]
        try:
            versions.append(f"pyyaml={importlib_metadata.version('PyYAML')}")
        except importlib_metadata.PackageNotFoundError:
            pass
        return versions

    def _current_user(self) -> str | None:
        try:
            return getpass.getuser()
        except Exception:
            return None

    @classmethod
    def from_files(
        cls,
        file_paths: Iterable[str | Path],
        *,
        name: str | None = None,
        backend: str = "python",
        config: PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None = None,
        dependencies: Mapping[str, Sequence[str]] | None = None,
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ) -> "Pipeline":
        stages: list[Stage] = []
        for file_path in file_paths:
            path = Path(file_path)
            stage_name = path.stem
            stage_dependencies = cls._dependencies_for_stage(stage_name, path, dependencies)
            stages.append(
                Stage.from_file(
                    path,
                    name=stage_name,
                    dependencies=stage_dependencies,
                    backend=backend,
                )
            )

        return cls(
            name=name or (stages[0].name if stages else "pipeline"),
            backend=backend,
            config=config,
            stages=stages,
            logger=logger,
            executor=executor,
        )

    @classmethod
    def from_dict(cls, cfg: Mapping[str, Any]) -> "Pipeline":
        payload = dict(cfg)

        name = payload.pop("name", None)
        backend = payload.pop("backend", "python")
        config = payload.pop("config", None)
        stages = payload.pop("stages", [])

        if config is None and payload:
            config = payload
        elif isinstance(config, Mapping) and payload:
            combined_config = dict(config)
            combined_config.update(payload)
            config = combined_config

        return cls(
            name=name,
            backend=backend,
            config=config,
            stages=stages,
        )

    @staticmethod
    def _dependencies_for_stage(
        stage_name: str,
        path: Path,
        dependencies: Mapping[str, Sequence[str]] | None,
    ) -> tuple[str, ...]:
        if not dependencies:
            return ()

        candidates = (stage_name, path.name, path.stem, str(path), path.as_posix())
        for candidate in candidates:
            if candidate in dependencies:
                return tuple(str(dependency) for dependency in dependencies[candidate])

        return ()