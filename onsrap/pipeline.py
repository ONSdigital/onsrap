from __future__ import annotations

import getpass
import hashlib
import subprocess
import warnings
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import StageConfigurationError, PipelineInitialisationError
from .warnings import StageConfigurationWarning
from .execution import PythonStageExecutor, StageExecutor
from .graph import StageGraph
from .logger import Logger
from .models import PipelineConfig, StageConfig, PipelineRun, RunManifest, RuntimeID, now
from .stage import Stage, _normalize_dependencies


ACCEPTED_CONFIG_TYPES = (".yaml", ".yml")

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
    ``config`` : PipelineConfig | Mapping[str, Any] | str | Path | None 
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
        config: PipelineConfig | Mapping[str, Any] | None = None,
        stages: Sequence[Stage | Mapping[str, Any] | str | Path | Callable[..., Any]] | None = None,
        dependencies: tuple[str]| dict[str, Sequence[str]] | None = None,
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ):
        # if config is not None:
        resolved_config, resolved_stage_configs, configured_stages = self._resolve_config(config)

        self.name = name or resolved_config.name or "pipeline"
        self.backend = backend or resolved_config.backend or "python"
        if backend == "python" and resolved_config.backend != "python":
            raise PipelineInitialisationError(f"Pipeline backend {backend} does not align with PipelineConfig backend {resolved_config.backend}.")

        self.config = resolved_config
        if self.config.name is None:
            self.config.name = self.name
        
        self.logger = logger or Logger(log_dir=self.config.log_dir)
        if executor is None:
            if self.backend == "python":
                self.executor = PythonStageExecutor()
            else:
                raise PipelineInitialisationError("Requested backend does not have a compatible executor. Available executors are: Python.")
        else: 
            self.executor = executor
        
        if stages is None:
            self.stages = configured_stages
        elif len(configured_stages) != 0:
            raise PipelineInitialisationError("Stages parsed through both Pipeline initialisation AND config file. Please choose one method.")
        else:
            self.stages = [self._coerce_stage(stage) for stage in stages]

        self.dependencies = dependencies
        if dependencies is not None and stages is None:
            raise PipelineInitialisationError("Stages need to be defined before you can parse your dependencies "
            "for those stages. Try the from_files() method, or create your Stage objects and " \
            "parse them to the Pipeline Constructor.")
        if dependencies is not None:
            self._assign_dependencies(dependencies, self.stages)

        self.stage_configs = dict(resolved_stage_configs)
        self._sync_stage_configs()
        # TODO: link with comment on issue #28 - We need to integrate StageGraph and validation
        # with stages_to_run which will be in PipelineConfig. This allows users to turn on and off Stages
        # but we haven't accounted for what that looks like in StageGraph/Pipeline orchestration.
        self.graph = StageGraph.from_stages(self.stages)
        self.graph.validate()
        self.id: RuntimeID | None = None
        self.manifest: RunManifest | None = None
        self.last_run: PipelineRun | None = None

        self.logger.event(
            "Pipeline initialized",
            name=self.name,
            backend=self.backend,
            stages=[stage.name for stage in self.stages],
        )
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
            self._sync_stage_configs()
            self._rebuild_graph()
            self.logger.event("Stage added", stages=[stage.name for stage in added_stages])
    
    def ordered_stages(self) -> list[Stage]:
            """
            Runs the topological_order() method on the ``graph`` attribute to extract the 
            correct order for the ``stages`` to be run in. 
            """
            return self.graph.topological_order()

    def validate(self) -> Pipeline:
        """
        Confirms that the source files for the stage exist. 
        """
        self.logger.event("Validating pipeline", name=self.name)
        self._validate_stage_configs()
        for stage in self.stages:
            stage.validate()
        self.graph.validate()
        return self
    
    def create_stage_config(
        self,
        s_config: Mapping[str, Any] | str | Path,
        *,
        name: str | None = None,
    ) -> StageConfig:
        """
        Create a ``StageConfig`` from direct data, a stage-name keyed mapping, or a config file.

        Parameters
        ----------
        ``s_config`` : Mapping[str, Any] | str | Path
            Either a single stage payload, a mapping keyed by stage name, or a config file.
            Config files may contain a top-level ``stage_configuration`` section or may consist
            solely of stage-name keyed configuration entries.
        ``name`` : str or None, keyword-only
            Stage name to extract when the input contains more than one stage configuration.

        Returns
        -------
        ``StageConfig``
            The normalized stage configuration for the requested stage.

        Raises
        ------
        ``StageConfigurationError``
            If the input cannot be resolved to exactly one stage configuration.
        """
        if isinstance(s_config, Mapping):
            if "pipeline_variables" in s_config or "stage_configuration" in s_config or "stage_config" in s_config:
                _, stage_config_payload = self._split_config_sections(s_config)
                stage_configs = self._build_stage_configs(stage_config_payload)
            elif name is not None and name in s_config and isinstance(s_config[name], Mapping):
                stage_configs = self._build_stage_configs(s_config)
            else:
                if name is None:
                    if len(s_config) != 1:
                        raise StageConfigurationError(
                            "A stage configuration mapping must include exactly one stage when no name is provided."
                        )
                    name, stage_payload = next(iter(s_config.items()))
                else:
                    stage_payload = s_config

                if not isinstance(stage_payload, Mapping):
                    raise StageConfigurationError("Stage configuration values must be provided as a mapping.")

                return StageConfig.from_mapping(str(name), stage_payload)

            return self._select_stage_config(stage_configs, name=name)

        raw_payload = self._load_config_mapping(s_config)
        if "pipeline_variables" in raw_payload or "stage_configuration" in raw_payload or "stage_config" in raw_payload:
            _, stage_config_payload = self._split_config_sections(raw_payload)
            stage_configs = self._build_stage_configs(stage_config_payload)
        elif all(isinstance(value, Mapping) for value in raw_payload.values()):
            stage_configs = self._build_stage_configs(raw_payload)
        else:
            raise StageConfigurationError(
                "Config files passed to create_stage_config must define a stage-configuration section or a mapping of stage names to configuration mappings."
            )

        return self._select_stage_config(stage_configs, name=name)

    def run(self) -> PipelineRun:
        """
        Returns an instance of ``PipelineRunner`` which actually runs the pipeline. 
        """
        from .runner import PipelineRunner
        
        return PipelineRunner(logger=self.logger).run(self)

    def add_dependencies(self,
                         *dependencies: tuple[str]| dict[str, Sequence[str]]) -> None:
        """
        Adds a set of ``dependencies`` for the Pipeline after the Pipeline initialisation. 

        This method takes any number of positional arguments and imputes them as
        ``dependencies``. It looks at each argument parsed, checks the data type against
        the existing ``Pipeline`` ``dependencies`` and if they are the same data type, it
        will take every stage within the ``Pipeline`` instance. It will then run the 
        ``_dependencies_for_stage()`` class method and normalize any ``dependencies`` before
        adding them to the individual ``Stage`` instances. It will then append these 
        ``dependencies`` directly to the ``dependencies`` in the ``Pipeline`` instance before
        rerunning the ``StageGraph`` creation to ensure the new ``dependencies`` are considered. 
        A logging entry will be created to track that these ``dependencies`` are added. 

        Parameters
        ----------
        ``*dependencies`` : tuple[str]| dict[str, Sequence[str]]
            Any number of dependencies that you would like to add to the Pipeline. 

        Raises
        ------
        ``PipelineInitializationError``
            If the dependency you are attempting to add to the Pipeline doesn't match 
            the datatype for dependencies currently in the Pipeline.
        """
        
        for dependency in dependencies:
            if self.dependencies is not None and not isinstance(dependency, type(self.dependencies)):
                raise PipelineInitialisationError("Existing dependencies are not the same type as new dependencies")
            
            for stage in self.stages:
                new_dependencies = self._dependencies_for_stage(stage.name, stage.source, dependency)
                existing = stage.dependencies or ()
                new = existing + tuple(_normalize_dependencies(new_dependencies))

                stage.dependencies = tuple(dict.fromkeys(new))
            
            if isinstance(dependency, tuple):
                existing = self.dependencies or ()
                self.dependencies = tuple(existing | dependency)
            elif isinstance(dependency, dict): 
                for stage_name, deps in dependency.items():
                    existing = self.dependencies.get(stage_name,[])
                    combined = existing + tuple(deps)
                    self.dependencies[stage_name] = tuple(dict.fromkeys(combined))

        self.graph = StageGraph.from_stages(self.stages)
        self.graph.validate()

        self.logger.event("New dependencies added to Pipeline instance and respective Stage instances",dependencies = dependencies)    



    def _assign_dependencies(self, 
                             dependencies:tuple[str]| dict[str, Sequence[str]] | None = None,
                             stages: Stage | Sequence[Stage] | None = None,) -> Stage | Sequence[Stage]:
        for stage in stages:
            new_dependencies = self._dependencies_for_stage(stage.name, stage.source, dependencies)
            stage.dependencies = _normalize_dependencies(new_dependencies)
            #TODO: Should this aldo return pipeline.dependencies as the normalised values?

        return stages

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
            parameters=self._manifest_parameters(),
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

    def _resolve_config(
        self,
        config: PipelineConfig | Mapping[str, Any] | None,
    ) -> tuple[PipelineConfig, dict[str, StageConfig], list[Stage]]:
        """
        Resolve supported configuration inputs into pipeline config, stage config, and stages.

        This method is the main normalization step for configuration injection. It accepts
        already-constructed config objects, raw mappings, and YAML files, and converts them
        into the three objects the pipeline needs before execution starts.
        """
        if config is None:
            return PipelineConfig.from_any(config), {}, []

        if isinstance(config, PipelineConfig):
            stage_configuration = config.metadata.get("stage_configuration", None)
            if stage_configuration is None:
                stage_configuration = config.metadata.get("stage_config", None)

            if stage_configuration is not None:
                warnings.warn(
                    "Stage configuration found in PipelineConfig metadata. This is supported for backwards compatibility but a composite config payload is preferred.",
                    StageConfigurationWarning,
                )
            return config, self._build_stage_configs(stage_configuration), []

        raw_config = self._load_config_mapping(config)
        pipeline_payload, stage_config_payload = self._split_config_sections(raw_config)
        normalized_pipeline_payload = self._normalize_pipeline_payload(pipeline_payload)

        # TODO: PipelineConfig needs to know what stages to run
        # Extract run order from stages

        #run_order = self._extract_run_order(pipeline_payload)
        # - Look for stages in pipeline_payload
        # - Create a dict, where keys are stage names, and values are where run = true or false
        # - Ensure through StageGraph at some point that dependencies are met.
        stage_definitions = normalized_pipeline_payload.pop("stages", ())

        pipeline_config = PipelineConfig.from_mapping(normalized_pipeline_payload)
        stage_configs = self._build_stage_configs(stage_config_payload)
        configured_stages = self._build_stages_from_config(
            stage_definitions,
            backend=pipeline_config.backend,
            work_dir=pipeline_config.work_dir,
        )
        return pipeline_config, stage_configs, configured_stages

    def _sync_stage_configs(self) -> None:
        """
        Ensure every known stage has a ``StageConfig`` entry, even if it is empty.
        """
        for stage in self.stages:
            self.stage_configs.setdefault(stage.name, StageConfig(name=stage.name))

    def _validate_stage_configs(self) -> None:
        """
        Confirm that every configured stage name matches a stage present in the pipeline.
        """
        self._sync_stage_configs()
        stage_names = {stage.name for stage in self.stages}
        unknown_stage_configs = sorted(name for name in self.stage_configs if name not in stage_names)
        if unknown_stage_configs and stage_names:
            missing = ", ".join(unknown_stage_configs)
            raise StageConfigurationError(
                f"Stage configuration was provided for unknown stages: {missing}."
            )

    def _manifest_parameters(self) -> dict[str, Any]:
        """
        Build the manifest parameter payload, including per-stage configuration.
        """
        parameters = self.config.to_dict()
        if self.stage_configs:
            parameters["stage_configuration"] = {
                name: stage_config.to_dict()
                for name, stage_config in self.stage_configs.items()
            }
        return parameters
    
    def _build_stages_from_config(
            self,
            stage_definitions: Sequence[Any] | None,
            *,
            backend: str,
            work_dir: Path,
        ) -> list[Stage]:
            """
            Convert configured stage definitions into ``Stage`` instances.

            Each entry is resolved independently, so the method can process any number of
            stage definitions supplied in the pipeline configuration.
            """
            if not stage_definitions:
                return []
            if not isinstance(stage_definitions, Sequence) or isinstance(stage_definitions, (str, bytes)):
                raise StageConfigurationError("Configured stages must be provided as a sequence.")

            configured_stages: list[Stage] = []
            for stage_definition in stage_definitions:
                stage = self._stage_from_config_definition(stage_definition, backend=backend, work_dir=work_dir)
                if stage is not None:
                    configured_stages.append(stage)
            return configured_stages

    def _stage_from_config_definition(
        self,
        stage_definition: Any,
        *,
        backend: str,
        work_dir: Path,
    ) -> Stage | None:
        """
        Resolve one configured stage entry into a ``Stage`` instance.

        Supported forms include ready-made ``Stage`` objects, paths, callables, full stage
        dictionaries, and compact ``{stage_name: {...}}`` definitions from YAML config files.
        Entries with ``run: false`` are skipped.
        """
        if isinstance(stage_definition, Stage):
            return stage_definition

        if isinstance(stage_definition, (str, Path)) or callable(stage_definition):
            return self._coerce_stage(stage_definition)

        if not isinstance(stage_definition, Mapping):
            raise StageConfigurationError("Configured stage entries must be mappings, paths, or callables.")

        payload = dict(stage_definition)
        if any(key in payload for key in ("name", "source", "path", "callable")):
            return Stage.from_dict(payload)

        if len(payload) != 1:
            raise StageConfigurationError(
                "Configured stage mappings must define exactly one stage name."
            )

        stage_name, stage_payload = next(iter(payload.items()))
        if not isinstance(stage_payload, Mapping):
            raise StageConfigurationError("Configured stage details must be provided as a mapping.")

        stage_options = dict(stage_payload)
        if not bool(stage_options.pop("run", True)):
            return None

        location = stage_options.pop("location", stage_options.pop("source", stage_options.pop("path", None)))
        dependencies = stage_options.pop("dependencies", ())
        entrypoint = stage_options.pop("entrypoint", None)
        metadata = stage_options.pop("metadata", {})
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {"metadata": metadata}
        metadata.update(stage_options)

        source = self._resolve_stage_source(stage_name=str(stage_name), location=location, work_dir=work_dir)
        return Stage.from_file(
            source,
            name=str(stage_name),
            dependencies=dependencies,
            metadata=metadata,
            entrypoint=entrypoint,
            backend=backend,
        )
    

    @classmethod
    def from_files(
        cls,
        file_paths: Iterable[str | Path],
        *,
        name: str | None = None,
        backend: str = "python",
        config: PipelineConfig | Mapping[str, Any] | str | Path | None = None,
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
        ``config`` : PipelineConfig | Mapping[str, Any] | str | Path | None
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
    def from_dict(
        cls,
        config: PipelineConfig | Mapping[str, Any] | str | Path,
        name: str | None = None,
        backend: str = "python",
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ) -> Pipeline:
        """
        Extracts information from a dictionary to configure a Pipeline instance as
        well as what the Pipeline runs. 

        Parameters 
        ----------
        ``config`` : PipelineConfig | Mapping[str, Any] | str | Path
            The object containing the information needed to run the Pipeline.
        
        Returns
        -------
        A ``Pipeline`` class instance. 
        """
        # TODO: Finish this class method to include missing variables and clarify where sourced from config.
        pipe_payload, stage_payload = cls._split_config_sections(config)

        # pipeline_variables contains pipeline information
        name = pipe_payload.pop("name", None)
        backend = pipe_payload.pop("backend", "python")
        stages = pipe_payload.pop("stages", [])

        return cls(
            name=name,
            backend=backend,
            config=pipe_payload,
            stages=stages,
        )

    @classmethod
    def from_config(
        cls,
        config: PipelineConfig | Mapping[str, Any] | str | Path,
        name: str | None = None,
        backend: str = "python",
        logger: Logger | None = None,
        executor: StageExecutor | None = None,
    ) -> Pipeline:
        """
        Construct a pipeline directly from a composite configuration payload or file.

        This is the preferred entrypoint when configuration defines both pipeline-level
        settings and the stage-level configuration that should be injected at runtime.
        """
        return cls.from_dict(
            config=config,
            name=name, 
            backend=backend, 
            logger=logger, 
            executor=executor
            )



    @staticmethod
    def _select_stage_config(
        stage_configs: Mapping[str, StageConfig],
        *,
        name: str | None,
    ) -> StageConfig:
        """
        Select one stage configuration from a stage-name keyed mapping.

        When ``name`` is omitted, exactly one stage configuration must be present.
        """
        if name is not None:
            if name not in stage_configs:
                raise StageConfigurationError(f"Stage configuration '{name}' was not found.")
            return stage_configs[name]

        if len(stage_configs) != 1:
            raise StageConfigurationError(
                "The provided input resolves to multiple stage configurations; specify a stage name."
            )

        return next(iter(stage_configs.values()))

    @staticmethod
    def _load_config_mapping(
        config: Mapping[str, Any] | str | Path,
    ) -> dict[str, Any]:
        """
        Load raw configuration data from a mapping or YAML file.
        """
        if isinstance(config, Mapping):
            return dict(config)

        config_path = Path(config).expanduser()
        if config_path.suffix.lower() not in ACCEPTED_CONFIG_TYPES:
            raise StageConfigurationError(
                f"Unsupported config file format parsed as Stage Configuration: {config!r}."
            )
        if not config_path.exists():
            raise FileNotFoundError(f"Config file does not exist: {config_path}")

        import yaml

        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if raw_config is None:
            # TODO: Warn if it fails?
            return {}
        if not isinstance(raw_config, Mapping):
            # TODO: maybe this should be richer error messaging
            raise TypeError("Pipeline config file must contain a mapping at the top level.")
        return dict(raw_config)

    @staticmethod
    def _split_config_sections(raw_config: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
        """
        Split a raw config payload into pipeline-level and stage-level sections.

        Composite config payloads may use top-level ``pipeline_variables`` and
        ``stage_configuration`` keys. Flat payloads are treated as pipeline config unless
        a stage-configuration key is present.
        """
        # TODO: Enforce this behaviour using Errors
        # TODO: Ensure that if stage_config or other keys grabbed are None, warn or error.
        # TODO: The if statement is messy and non-intuitive
        if "pipeline_variables" in raw_config or "stage_configuration" in raw_config or "stage_config" in raw_config:
            pipeline_payload = raw_config.get("pipeline_variables", {})
            if not isinstance(pipeline_payload, Mapping):
                raise StageConfigurationError("The 'pipeline_variables' section must be a mapping.")
            stage_payload = raw_config.get("stage_configuration", raw_config.get("stage_config"))
            return dict(pipeline_payload), stage_payload

        pipeline_payload = dict(raw_config)
        # The line below may never happen as it asks for "stage_config" but the if statement above also does this,
        # and this code only actions if that if statement does not complete. 
        stage_payload = pipeline_payload.pop("stage_configuration", pipeline_payload.pop("stage_config", None))
        return pipeline_payload, stage_payload

    @staticmethod
    def _normalize_pipeline_payload(pipeline_payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        Normalize supported aliases in the pipeline section before model construction.

        Recognized aliases:

        - ``working_dir`` → ``work_dir`` (only when ``work_dir`` is absent).

        If both ``working_dir`` and ``work_dir`` are present at the same time, a
        ``UserWarning`` is emitted and ``working_dir`` is left in the payload where
        it will be silently absorbed into ``PipelineConfig.metadata``.
        """
        normalized_payload = dict(pipeline_payload)
        if "working_dir" in normalized_payload:
            if "work_dir" not in normalized_payload:
                normalized_payload["work_dir"] = normalized_payload.pop("working_dir")
            else:
                warnings.warn(
                    "Both 'working_dir' and 'work_dir' were found in the pipeline configuration. "
                    "'work_dir' will be used and 'working_dir' will be ignored.",
                    UserWarning,
                    stacklevel=2,
                )
        return normalized_payload

    @staticmethod
    def _build_stage_configs(stage_configuration: Mapping[str, Any] | None) -> dict[str, StageConfig]:
        """
        Build a stage-name keyed configuration mapping for any number of configured stages.

        The returned mapping scales linearly with the provided stage entries and is used as
        the canonical runtime lookup structure for stage configuration.
        """
        if stage_configuration is None:
            return {}
        if not isinstance(stage_configuration, Mapping):
            raise StageConfigurationError("Stage configuration must be a mapping keyed by stage name.")

        return {
            str(stage_name): StageConfig.from_mapping(str(stage_name), stage_payload)
            for stage_name, stage_payload in stage_configuration.items()
        }

    
    @staticmethod
    def _resolve_stage_source(stage_name: str, location: Any, work_dir: Path) -> Path:
        """
        Resolve the source path for a configured stage.

        Empty locations default to ``work_dir / "scripts" / "<stage_name>.py"``. Relative
        paths are first interpreted as given and then relative to ``work_dir``.
        """
        if location in (None, ""):
            return work_dir / "scripts" / f"{stage_name}.py"

        candidate = Path(location).expanduser()
        if candidate.is_absolute() or candidate.exists():
            return candidate

        work_dir_candidate = work_dir / candidate
        if work_dir_candidate.exists():
            return work_dir_candidate

        return candidate

    @staticmethod
    def _dependencies_for_stage(
        stage_name: str,
        path: Path | Callable[..., Any] | None = None,
        dependencies: Mapping[str, Sequence[str]] | None = None,
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
        if isinstance(path, Path):
            candidates = (stage_name, path.name, path.stem, str(path), path.as_posix())
        else:
            candidates = (stage_name, str(path.__name__)) 
        for candidate in candidates:
            if candidate in dependencies:
                return tuple(str(dependency) for dependency in dependencies[candidate])

        return ()
