from __future__ import annotations

import getpass
import hashlib
import subprocess
import warnings
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import StageConfigurationError
from .warnings import StageConfigurationWarning
from .execution import PythonStageExecutor, StageExecutor
from .graph import StageGraph
from .logger import Logger
from .models import PipelineConfig, StageConfig, PipelineRun, RAPConfig, RunManifest, RuntimeID, now
from .stage import Stage



class Pipeline:
    """
    Represents an end-to-end code run. This class brings together class instances 
    from other modules within the package to establish what the Pipeline is. 

    Sets up the metadata, configurations, logging, and executors required to run the 
    Pipeline. Assigns multiple attributes including those not initialised such as, 
    ``id``, ``graph``, ``manifest``, and ``last_run``. These take the forms of other 
    classes defined in other modules within this package. 

    Parameters
    ----------
    ``name`` : str or None
        What the pipeline is called.
    ``backend`` : str, default = "python"
        The system used to run the pipeline. 
    ``config`` : PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None 
        The instance containing the required information on running the Pipeline. 
    ``stages`` : sequence of Stage, Mapping[str, Any], str, Path, Callable, or None. 
        The required steps within the Pipeline. 
    ``logger`` : Logger or None
        The system that is used to track the progress of the Pipeline. 
    ``executor`` : StageExecutor or None
        The way that the Pipeline is actively run. 
    """
    def __init__(
        self,
        name: str | None = None,
        backend: str = "python",
        config: PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None = None,
        stages: Sequence[Stage | Mapping[str, Any] | str | Path | Callable[..., Any]] | None = None,
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ):
        self.backend = backend or "python"
        self.config = PipelineConfig.from_any(config)
        if (self.config.name is not None) and (name == None):
            self.name = self.config.name
        else:
            self.name = name or "pipeline"

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
        """
        Extracts the ``Stage`` information from the provided stages in the Pipeline. 

        Enables mappings, strings, paths, or callables to be parsed and converted into 
        a useable ``Stage`` class instance. If a ``Stage`` class instance is parsed, return 
        itself. 

        Parameters
        ----------
        ``stage`` : Stage | Mapping[str, Any] | str | Path | Callable[..., Any]
            The information attempting to be converted into a ``Stage`` class instance.

        Raises
        ------
        ``StageConfigurationError``
            If the information parsed is not in a suitable format to be converted into 
            a ``Stage`` class instance. 

        Returns
        -------
        ``Stage`` class instance for the stage being run. 
        """
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
        """
        Updates the ``graph`` attribute with the latest stage information. 
        """
        self.graph = StageGraph.from_stages(self.stages)

    def add_stage(self, *stages: Stage | Mapping[str, Any] | str | Path | Callable[..., Any]) -> None:
        """
        Adds a step to the Pipeline.

        Creates a list called ``added_stages`` that runs the _coerce_stage() method
        to extract the information from the given ``stages`` parameter. It then appends
        this list to the ``stages`` attribute of the ``Pipeline`` class and updates the 
        StageGraph using the _rebuild_graph() method. A log instance is created to 
        reflect the changes. 

        Parameters
        ----------
        ``stages`` : Stage | Mapping[str, Any] | str | Path | Callable[..., Any]
            The new steps being added to the Pipeline. 
        """
        added_stages = [self._coerce_stage(stage) for stage in stages]
        self.stages.extend(added_stages)
        self._rebuild_graph()
        self.logger.event("Stage added", stages=[stage.name for stage in added_stages])

    def ordered_stages(self) -> list[Stage]:
        """
        Runs the topological_order() method on the ``graph`` attribute to extract the 
        correct order for the ``stages`` to be run in. 
        """
        return self.graph.topological_order()

    def validate(self) -> "Pipeline":
        """
        Confirms that the source files for the stage exist. 
        """
        self.logger.event("Validating pipeline", name=self.name)
        for stage in self.stages:
            stage.validate()
        self.graph.validate()
        return self
    
    def create_stage_config(self, s_config: str | Path) -> StageConfig:
        pass

    def run(self) -> PipelineRun:
        """
        Returns an instance of ``PipelineRunner`` which actually runs the pipeline. 
        """
        from .runner import PipelineRunner
        
        return PipelineRunner(logger=self.logger).run(self)

    def _construct_manifest(self, *, runtime_id: RuntimeID) -> RunManifest:
        """
        Creates a ``RunManifest`` instance that contains the information about 
        the run of the Pipeline. 

        Parameters
        ----------
        ``runtime_id`` : RuntimeID
            Contains information about the run to be extracted and placed into 
            the ``RunManifest`` instance. 
        """
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
        """
        Creates a RuntimeID instance for the specific run. 

        Establishes attributes for this specific run and returns 
        as a ``RuntimeID`` instance. 
        """
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
        """
        Finds the specific version of the repository used for this run. 

        Attempts to run a Git command to establish the current git commit hash
        to be held in the ``RunManifest`` instance for this run. 

        Returns
        -------
        ``OSError``
            If Git is unable to be loaded or the Git command cannot be run for
            another reason. 
        """
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
        """
        Creates a list of packages and their versions used in this run. 

        Raises
        ------
        ``importlib_metadata.PackageNotFoundError``
            If the package used cannot be found in the library. 
        """
        versions = [f"python={sys.version.split()[0]}"]
        try:
            versions.append(f"pyyaml={importlib_metadata.version('PyYAML')}")
        except importlib_metadata.PackageNotFoundError:
            pass
        return versions

    def _current_user(self) -> str | None:
        """
        Extracts the username for the individual completing the run. Returns a blank 
        value if the username cannot be extracted. 
        """
        try:
            return getpass.getuser()
        except Exception:
            return None

    def _resolve_config(self, config: PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None) -> list[PipelineConfig, StageConfig] | PipelineConfig | StageConfig:
        if config is None:
            return PipelineConfig.from_any(config)
        if isinstance(config, str):
            if config.endswith(".yaml") or config.endswith(".yml"):
                return PipelineConfig.from_yaml(config)
            else:
                raise StageConfigurationError(f"Unsupported config file format parsed as Stage Configuration: {config!r}.")
        if isinstance(config, Path):
            if config.suffix in (".yaml", ".yml"):
                return PipelineConfig.from_yaml(config)
            else:
                raise StageConfigurationError(f"Unsupported config file format parsed as Stage Configuration: {config!r}.")
        if isinstance(config, PipelineConfig):
            if "stage_config" in config.metadata:
                warnings.warn(
                    "Stage Configuration found in PipelineConfig metadata. This should be moved to a separate location for StageConfiguration instantiation.",
                    StageConfigurationWarning
                )
                self.logger.warning(
                    "Stage Configuration found in PipelineConfig metadata. This should be moved to a separate location for StageConfiguration instantiation."
                )
            else:
                warnings.warn(
                    "No Stage Configuration found in parsed configuration. This may lead to unexpected behavior during pipeline execution.",
                    StageConfigurationWarning
                )
                self.logger.warning(
                    "No Stage Configuration found in parsed configuration. This may lead to unexpected behavior during pipeline execution."
                )
            return config
        if isinstance(config, Mapping):
            # Look for Pipeline Configuration and Stage Configuration in keys
            pass
        
        pipeline_config = self.config
        stage_config = StageConfig()
        return [pipeline_config, stage_config]


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
    ) -> Pipeline:
        """
        Extracts the information from files regarding exactly what is being run in the pipeline and
        allows for configuration of how the Pipeline is run. 

        Parameters
        ----------
        ``file_paths`` : Iterable[str or Path]
            The files that contain the code for each stage in the pipeline. These are what
            the Pipeline will run. 
        ``name`` : str
            The name of the pipeline.
        ``backend`` : str, default = "python"
            The system that the pipeline is written in. 
        ``config`` : PipelineConfig | RAPConfig | Mapping[str, Any] | str | Path | None
            The high level information required to run this specific pipeline. 
        ``dependencies`` : Mapping[str, Sequence[str]] or None
            An object containing which stages are required to be run before other stages. 
        ``logger`` : Logger class or None
            The logging sysem used for this Pipeline run. 
        ``executor`` : StageExecutor class or None
            The information on exactly how to run the Pipeline. 

        Returns 
        -------
        A ``Pipeline`` class instance. 
        """
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
        """
        Extracts information from a dictionary to configure a Pipeline instance as
        well as what the Pipeline runs. 

        Parameters 
        ----------
        ``cfg`` : Mapping[str, Any]
            The Mapping item that contains the information needed to run the Pipeline. 
        
        Returns
        -------
        A ``Pipeline`` class instance. 
        """
        payload = dict(cfg)

        # pipeline_variables contains pipeline information
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

    def from_config(cls, config: dict) -> Pipeline:
        # Wrapper for from_dict but expecting config Path/str or yaml object 
        # Extract pipeline_variables aka do not parse stage_configuration section of config.yaml
        pass

    @staticmethod
    def _dependencies_for_stage(
        stage_name: str,
        path: Path,
        dependencies: Mapping[str, Sequence[str]] | None,
    ) -> tuple[str, ...]:
        """
        Extracts a tuple of ``dependencies`` for the requested stage. 

        Will return a blank tuple if there are no ``dependencies`` for the requested
        stage. Allows for ``dependencies`` to be found regardless of how the stage is 
        referenced in the ``dependencies`` mapping. 

        Parameters
        ----------
        ``stage_name`` : str
            The name of the stage that you are extracting the ``dependencies`` for. 
        ``path`` : Path
            The filepath for the stage source. 
        ``dependencies`` : Mapping[str, Sequence[str]] or None
            Mapping of the stage source name to their relevant ``dependencies`` (stages
            required to run before the ``stage_name`` Stage). 
        """
        if not dependencies:
            return ()

        candidates = (stage_name, path.name, path.stem, str(path), path.as_posix())
        for candidate in candidates:
            if candidate in dependencies:
                return tuple(str(dependency) for dependency in dependencies[candidate])

        return ()