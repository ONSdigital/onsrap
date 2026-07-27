from __future__ import annotations

import getpass
import hashlib
import subprocess
import warnings
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import StageConfigurationError, PipelineInitialisationError, PipelineConfigurationError
from .warnings import StageConfigurationWarning, PipelineConfigurationWarning
from .execution import PythonStageExecutor, StageExecutor
from .graph import StageGraph
from .logger import Logger
from .models import PipelineConfig, StageConfig, PipelineRun, RunManifest, RuntimeID, now
from .stage import Stage, _normalize_dependencies


ACCEPTED_CONFIG_TYPES = (".yaml", ".yml")
AVAILABLE_EXECUTORS = ("python",)

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
        resolved_config, resolved_stage_configs, configured_stages, resolved_global_config = self._resolve_config(config)

        self.name = name or resolved_config.name or "pipeline"
        self.backend = backend or resolved_config.backend or "python"
        if backend == "python" and resolved_config.backend != "python":
            raise PipelineInitialisationError(f"Pipeline backend {backend} does not align with PipelineConfig backend {resolved_config.backend}.")

        self.config = resolved_config
        if self.config.name is None:
            self.config.name = self.name
        
        self.logger = logger or Logger(log_dir=self.config.log_dir)
        if executor is not None:
            self.executor = executor
        else:
            if self.backend == "python":
                self.executor = PythonStageExecutor()
            else:
                raise PipelineInitialisationError(f"Requested backend does not have a compatible executor. Available executors are: {', '.join(AVAILABLE_EXECUTORS)}.")
            
        if stages is not None and configured_stages:
            raise PipelineInitialisationError(
                "Stages parsed through both Pipeline construction and configuration file. Either provide stages through the constructor or the configuration file, not both."
            )
        self.stages = (
            configured_stages
            if stages is None
            else [self._coerce_stage(stage) for stage in stages]
        )

        self.dependencies = dependencies
        if dependencies is not None and stages is None:
            raise PipelineInitialisationError("Stages need to be defined before you can parse your dependencies "
            "for those stages. Try the from_files() method, or create your Stage objects and " \
            "parse them to the Pipeline Constructor.")
        if dependencies is not None:
            self._assign_dependencies(dependencies, self.stages)

        self.stage_configs = dict(resolved_stage_configs)
        self.global_configs = dict(resolved_global_config)
        
        self._sync_stage_configs()
        self._rebuild_graph()
        self.id: RuntimeID | None = None
        self.manifest: RunManifest | None = None
        self.last_run: PipelineRun | None = None

        self.logger.event(
            "Pipeline initialized",
            name=self.name,
            backend=self.backend,
            stages=[stage.name for stage in self.stages],
            enabled_stages=[stage.name for stage in self.graph.stages],
        )

    def __str__(self) -> str:
        """
        String method that returns a human-readable representation of the ``Pipeline`` class.

        Returns
        -------
        str
            A string representation of the ``Pipeline`` class with its attributes.
        """
        stages = "\n".join(f"{str(stage)}\n" for stage in self.stages)
        graph = [stage.name for stage in self.graph.stages]
        return (
            f"\nPipeline Instance Attributes\n"
            f"--------------------------\n"
            f"Name:\n    {self.name}\n\nBackend:\n     {self.backend} \n\n"
            f"Configuration:\n{self.config}\n\nStages:\n{stages} \n"
            f"Dependencies:\n     {self.dependencies} \n\nLogger:\n     {self.logger} \n\n"
            f"Executor:\n     {self.executor} \n\nGraph:\n     {graph} \n\n"
            f"ID:\n     {self.id} \n\nManifest:\n     {self.manifest} \n\nLast Run:\n     {self.last_run}\n"
        )

    def __repr__(self) -> str:
        """
        Representation method that returns a human readable representation of the ``Pipeline`` class. 
        This method is structured to be more concise than the ``__str__`` method and is 
        intended for debugging purposes.

        Returns 
        -------
        str
            A string representation of the ``Pipeline`` class with its attributes.
        """
        return (
            f"Pipeline(name={self.name}, backend={self.backend}, "
            f"stages={self.stages}, dependencies={self.dependencies}, "
            f"logger={self.logger}, executor={self.executor}, graph={self.graph}, "
            f"id={self.id}, manifest={self.manifest}, last_run={self.last_run})"
        )

    def add_stage(
        self,
        *stages: Stage | Mapping[str, Any] | str | Path | Callable[..., Any],
        stage_configs: StageConfig | Mapping[str, Any] | str | Path | Iterable[StageConfig | Mapping[str, Any] | str | Path] | None = None,
        enable_stages: bool = False,
    ) -> None:
        """
        Adds one or more steps to the Pipeline.

        ``enable_stages`` : bool, default False
            Whether to enable the added stages immediately. Default is False and is recommended.

        Creates a list called ``added_stages`` that runs the _coerce_stage() method
        to extract the information from the given ``stages`` parameter. It then appends
        this list to the ``stages`` attribute of the ``Pipeline`` class, adds any stage
        configuration that was provided alongside those stages, and updates the StageGraph
        using the _rebuild_graph() method.

        Parameters
        ----------
        ``stages`` : Stage | Mapping[str, Any] | str | Path | Callable[..., Any]
            The new steps being added to the Pipeline.
        ``stage_configs`` : StageConfig | Mapping[str, Any] | str | Path | Iterable[StageConfig | Mapping[str, Any] | str | Path] | None
            Optional stage configuration payloads to add alongside the stages.
        """
        if not stages:
            warnings.warn(
                "No stages provided to add_stage(). No changes made to the Pipeline.",
                PipelineConfigurationWarning,
            )
            return

        added_stages = [self._coerce_stage(stage) for stage in stages]
        parsed_stage_configs: list[StageConfig] = []

        if stage_configs is not None:
            if isinstance(stage_configs, Mapping) and all(isinstance(value, Mapping) for value in stage_configs.values()):
                raw_stage_configs = [
                    {str(stage_name): stage_payload}
                    for stage_name, stage_payload in stage_configs.items()
                ]
            elif isinstance(stage_configs, (StageConfig, Mapping, str, Path)):
                raw_stage_configs = [stage_configs]
            else:
                raw_stage_configs = list(stage_configs)

            if len(raw_stage_configs) != len(added_stages):
                warnings.warn(
                    "The number of stage configurations passed to add_stage() does not match the number of stages. "
                    f"Received {len(raw_stage_configs)} stage configuration(s) for {len(added_stages)} stage(s).",
                    StageConfigurationWarning,
                )

            known_stage_names = {stage.name for stage in self.stages}
            known_stage_names.update(stage.name for stage in added_stages)

            for index, raw_stage_config in enumerate(raw_stage_configs):
                stage_name = added_stages[index].name if index < len(added_stages) else None
                parsed_stage_config = self._coerce_stage_config(raw_stage_config, name=stage_name)
                if parsed_stage_config.name not in known_stage_names:
                    raise StageConfigurationError(
                        f"Stage configuration was provided for unknown stage: {parsed_stage_config.name}."
                    )
                parsed_stage_configs.append(parsed_stage_config)

        self.stages.extend(added_stages)

        for conf in parsed_stage_configs:
            self.add_stage_config(conf)

        self._register_added_stages_in_stage_selection(added_stages, enable_stages=enable_stages)
        self._check_stage_configs(added_stages, self.stage_configs)

        self._sync_stage_configs()
        self._rebuild_graph()

        self.logger.event(
            "Stage added",
            stages=[stage.name for stage in added_stages],
            stage_configs=[stage_config.name for stage_config in parsed_stage_configs],
        )

    def add_stage_config(
        self,
        stage_config: StageConfig | Mapping[str, Any] | str | Path,
        *,
        name: str | None = None,
    ) -> None:
        """
        Add or replace a ``StageConfig`` attached to the Pipeline.

        Parameters
        ----------
        ``stage_config`` : StageConfig | Mapping[str, Any] | str | Path
            The stage configuration information to add to the Pipeline.
        ``name`` : str or None, keyword-only
            Optional stage name used when the parsed configuration payload does not
            identify the stage on its own.
        """
        parsed_stage_config = self._coerce_stage_config(stage_config, name=name)
        self.stage_configs[parsed_stage_config.name] = parsed_stage_config
        self.logger.event("Stage configuration added", stage=parsed_stage_config.name)
    
    def enable_stage(self, *stage_name: str | list[str]) -> None:
        """
        Mark one or more stages as enabled in the run selection.

        In implicit "run all" mode (``stages_to_run`` is empty), this is a no-op
        because every registered stage already participates in the execution graph.
        In explicit mode the requested stages are marked ``True`` in
        ``stages_to_run`` and the execution graph is rebuilt to reflect the change.

        Parameters
        ----------
        ``stage_name`` : str or list[str]
            One or more stage names to enable.
        """
        stage_names = set()
        for name in stage_name:
            if isinstance(name, list):
                stage_names.update(name)
            else:
                stage_names.add(name)

        if not stage_names.issubset({stage.name for stage in self.stages}):
            raise PipelineInitialisationError("You're trying to enable a stage that does not exist in the Pipeline. Please add the stage to the Pipeline.")

        if not self.config.stages_to_run:
            return

        for name in stage_names:
            self.config.stages_to_run[name] = True
        self._rebuild_graph()
        self.logger.event("Stages enabled", stages=sorted(stage_names))

    def disable_stage(self, *stage_name: str | list[str]) -> None:
        """
        Mark one or more stages as disabled in the run selection.

        When in implicit "run all" mode (``stages_to_run`` is empty), calling
        ``disable_stage`` switches the pipeline into explicit stage-selection mode:
        every currently registered stage is first marked enabled, then the requested
        stages are set to ``False``. The execution graph is rebuilt after the change.

        Parameters
        ----------
        ``stage_name`` : str or list[str]
            One or more stage names to disable.
        """
        stage_names = set()
        for name in stage_name:
            if isinstance(name, list):
                stage_names.update(name)
            else:
                stage_names.add(name)

        if not stage_names.issubset({stage.name for stage in self.stages}):
            raise PipelineInitialisationError("You're trying to disable a stage that does not exist in the Pipeline. Please add the stage to the Pipeline.")

        if not self.config.stages_to_run:
            self.config.stages_to_run = {stage.name: True for stage in self.stages}

        for name in stage_names:
            self.config.stages_to_run[name] = False
        self._rebuild_graph()
        self.logger.event("Stages disabled", stages=sorted(stage_names))

    def ordered_stages(self) -> list[Stage]:
        """
        Return the effective stages in dependency-respecting execution order.

        This is the primary method used by ``PipelineRunner`` to determine what to
        execute. Only stages that are part of the current execution graph appear
        here; stages disabled via ``PipelineConfig.stages_to_run`` are absent even
        if they are registered in ``Pipeline.stages``.
        """
        return self.graph.topological_order()

    def validate(self) -> Pipeline:
        """
        Confirm that the pipeline is ready to run.

        Validates source files for every stage in the current execution graph,
        checks that all stage-configuration names correspond to a known stage, and
        validates the execution graph for structural consistency. Disabled stages
        are excluded from source-file validation because they will not be executed.
        """
        self.logger.event(
            "Validating pipeline",
            name=self.name,
            stages=len(self.stages),
            enabled_stages=len(self.graph.stages),
        )
        self._validate_stage_configs()
        for stage in self.graph.stages:
            stage.validate()
        self.graph.validate()
        return self
    

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

    def _coerce_stage_config(
        self,
        stage_config: StageConfig | Mapping[str, Any] | str | Path,
        *,
        name: str | None = None,
    ) -> StageConfig:
        """
        Normalize supported stage-configuration inputs into a ``StageConfig``.
        """
        if isinstance(stage_config, StageConfig):
            if name is not None and stage_config.name != name:
                raise StageConfigurationError(
                    f"Stage configuration '{stage_config.name}' does not match stage '{name}'."
                )
            return stage_config

        if isinstance(stage_config, Mapping):
            if name is not None and all(isinstance(value, Mapping) for value in stage_config.values()) and name not in stage_config:
                available_stage_names = ", ".join(str(stage_name) for stage_name in stage_config)
                raise StageConfigurationError(
                    f"Stage configuration '{name}' was not found. Available stage configurations are: {available_stage_names}."
                )
            return self.create_stage_config(stage_config, name=name)

        if isinstance(stage_config, (str, Path)):
            return self.create_stage_config(stage_config, name=name)

        raise StageConfigurationError(f"Unsupported stage configuration specification: {type(stage_config)!r}.")

    def _rebuild_graph(self) -> None:
        """
        Update and validate the execution graph.
        The execution graph is a subset of the full Stage registry 
        (Pipeline.stages), reflecting the stages that are actually enabled 
        for execution.

        The pipeline keeps ``self.stages`` as the complete stage registry, but
        ``self.graph`` represents the effective run set after applying
        ``PipelineConfig.stages_to_run`` and expanding any selected stage's
        dependencies.
        """
        stages_to_run = self._resolve_stages_to_run()
        self.graph = StageGraph.from_stages(stages_to_run)
        self.graph.validate()

    def _register_added_stages_in_stage_selection(self, stages: Sequence[Stage], enable_stages: bool = False) -> None:
        """
        Default newly added stages to disabled once explicit stage selection is in use.

        When ``stages_to_run`` is empty, the pipeline is in implicit "run all"
        mode and new stages should immediately participate in the execution graph.
        Once the configuration has switched to an explicit stage-selection mapping,
        newly added stages stay out of the execution graph until they are enabled.
        """
        if not self.config.stages_to_run:
            return

        for stage in stages:
            self.config.stages_to_run.setdefault(stage.name, enable_stages)


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
            inputs={stage.name: list(stage.dependencies) for stage in self.graph.stages},
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
        pipeline_payload, stage_config_payload, global_config_payload = self._split_config_sections(raw_config)
        normalized_pipeline_payload = self._normalize_pipeline_payload(pipeline_payload)

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

            stage_definitions = list(stage_definitions)

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
    
    def _resolve_stages_to_run(self) -> list[Stage]:
        """
        Resolve the effective stage subset that should populate the execution graph.

        An empty ``stages_to_run`` mapping means the pipeline runs all known stages.
        Otherwise, stages explicitly marked ``True`` are selected and their transitive
        dependencies are pulled in automatically. A dependency that is explicitly
        disabled in ``stages_to_run`` while another enabled stage requires it raises
        a ``PipelineConfigurationError``.
        """
        stage_lookup = {stage.name: stage for stage in self.stages}
        configured_stages_to_run = dict(self.config.stages_to_run or {})

        # When PipelineConfig.stages_to_run is empty, the pipeline is in implicit "run all" mode.
        if not configured_stages_to_run:
            return self.stages

        unknown_stage_names = sorted(
            stage_name
            for stage_name in configured_stages_to_run
            if stage_name not in stage_lookup
        )
        if unknown_stage_names:
            missing = ", ".join(unknown_stage_names)
            raise PipelineInitialisationError(
                f"Pipeline configuration references unknown stages in stages_to_run: {missing}."
            )

        explicitly_enabled = [
            stage_name
            for stage_name, value in configured_stages_to_run.items()
            if value
        ]
        if not explicitly_enabled:
            return []

        explicitly_disabled = {
            stage_name
            for stage_name, value in configured_stages_to_run.items()
            if not value
        }
        resolved_stage_names: set[str] = set()
        visiting: set[str] = set()

        def add_stage_with_dependencies(stage_name: str, *, required_by: str | None = None) -> None:
            """
            Add one selected stage and recursively include everything it depends on.

            ``_resolve_stages_to_run()`` uses this helper to turn the user-facing
            ``stages_to_run`` selection into a runnable execution set for the
            ``StageGraph``. It also guards against invalid configurations where an
            enabled stage depends on a stage that has been explicitly disabled.
            """
            if stage_name in resolved_stage_names:
                return
            if required_by is not None and stage_name in explicitly_disabled:
                raise PipelineConfigurationError(
                    f"Stage '{required_by}' is enabled but depends on disabled stage '{stage_name}'."
                )
            if stage_name in visiting:
                return
            if stage_name not in stage_lookup:
                raise PipelineInitialisationError(
                    f"You're trying to run a stage that does not exist: '{stage_name}'. Please add the stage to the Pipeline."
                )

            visiting.add(stage_name)
            resolved_stage_names.add(stage_name)
            for dependency_name in stage_lookup[stage_name].dependencies:
                add_stage_with_dependencies(dependency_name, required_by=stage_name)
            visiting.remove(stage_name)

        for stage_name in explicitly_enabled:
            add_stage_with_dependencies(stage_name)

        return [stage for stage in self.stages if stage.name in resolved_stage_names]

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
        # REMOVED AS THIS WAS RUNNING TWICE. SHOULD DISCUSS WHAT TO DO ABOUT THIS 
        #METHOD AND WHETHER IT IS NEEDED
        
        #pipe_payload, stage_payload = cls._split_config_sections(config)

        # pipeline_variables contains pipeline information
        #name = pipe_payload.get("name", None)
        #backend = pipe_payload.get("backend", "python")
        #stages = pipe_payload.get("stages", [])
        #print(stages)

        return cls(
            name=name,
            backend=backend,
            config=config,
            stages=None,
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
        extracted_config = Pipeline._load_config_mapping(config)

        return cls.from_dict(
            config=extracted_config,
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
            warnings.warn("No configuration has loaded from the configuration file. Please check " \
            "your configurations.")
            return {}
        if not isinstance(raw_config, Mapping):
            raise TypeError("Configuration file must contain a mapping at the top level. Please ensure" \
            "that your configuration file is structured into key:value pairs in the notation that suits" \
            "the configuration file that you are using. The top level key value pairs should reflect " \
            "the Pipeline and Stage configurations.")
        return dict(raw_config)

    @staticmethod
    def _split_config_sections(raw_config: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """
        Split a raw config payload into pipeline-level and stage-level sections.

        Allows for configurations that have "stage_configuration", "stage_config", "pipeline_variables"
        and "pipeline_config" as the key. The key is identified and used to pull the values for the 
        configuration from the ``raw_config``. It is then Nonetype checked and Type checked to ensure 
        that appropriate information is extracted and errors are produced if any of these checks fail. 

        Parameters
        ----------
        ``raw_config``: Mapping[str, Any]
            Contents of the configuration file previously extracted. 

        Returns 
        -------
        ``pipeline_payload``: Mapping[str, Any] | None
            Contents of the pipeline configuration settings defined in the configuration file. 
        ``stage_payload``: Mapping[str, Any] | None
            Contents of the stage configuration settings defined in the configuration file. 
        ``global_payload``: Mapping[str, Any] | None
            Contents of the global configuration settings defined in the configuration file.

        Raises
        ------
        ``PipelineConfigurationWarning`` 
            If blank values for pipeline_payload or global_payload are detected. 
            If there are remaining keys in the ``raw_config`` that have not been extracted. 

        ``StageConfigurationWarning``
            If blank values for stage_payload are detected.

        ``PipelineConfigurationError`` 
            If the pipeline_payload, global_payload or stage_payload are not mapping types. 
        """
        possible_stage_keys = ("stage_configuration", "stage_config")
        possible_pipeline_keys = ("pipeline_variables","pipeline_config")
        possible_global_keys = ("global_configuration", "global_config")

        stage_payload, stage_configuration = Pipeline._extract_mappings(possible_stage_keys, raw_config, StageConfigurationWarning)
        pipeline_payload, pipeline_configuration = Pipeline._extract_mappings(possible_pipeline_keys, raw_config, PipelineConfigurationWarning)
        global_payload, global_configuration = Pipeline._extract_mappings(possible_global_keys, raw_config, PipelineConfigurationWarning)

        remaining_keys = set(raw_config) - {pipeline_configuration, stage_configuration, global_configuration}
        if remaining_keys:
            warnings.warn("There are remaining sections in your configuration file that have not been extracted. Please check that all your configurations are in the pipeline or stage configuration keys.", 
            PipelineConfigurationWarning)

        return pipeline_payload, stage_payload, global_payload

    @staticmethod
    def _extract_mappings(keys: tuple[str,...],
                          config: Mapping[str, Any],
                          warning: PipelineConfigurationWarning | StageConfigurationWarning) -> tuple[dict[str, Any], str]:

        configuration = Pipeline._extract_keys(keys, config)
        payload = config.get(configuration,{})
        if payload is None: 
            warnings.warn(f"Blank {configuration} configuration detected. Please check that this is correct.", warning)
        if not isinstance(payload, Mapping):
            raise PipelineConfigurationError(f"The {configuration} section must be a mapping.")
        return payload, configuration


    @staticmethod
    def _extract_keys(possible_keys: tuple[str, ...],
                          dictionary: Mapping[str, Any]) -> str:
        """
        Checks whether a provided dictionary has a key that has been previously defined. 

        Creates a list for all specified keys that are present in the dictionary and checks
        the number of keys that match. This should only be 1 so if there are any fewer or 
        additional then appropriate errors are raised. 

        Parameters 
        ----------
        ``possible_keys``: tuple[str, ...]
            Set of string keys that are possibly in the dictionary provided. 
        ``dictionary``: Mapping[str, Any]
            Dictionary that is being checked for valid keys. 

        Returns 
        -------
        ``key``: str
            String value for the key that is present in the ``dictionary`` out of the 
            ``possible_keys`` values. 

        Raises 
        ------ 
        ``PipelineConfigurationError``
            If no keys in the ``dictionary`` are also in the ``possible_keys`` tuple. 

        ``PipelineConfigurationWarning``
            If more than one key in the possible_keys is found, alerts user that it will 
            default to the first selected option and records the key that is selected.
        """
        
        matches = [key for key in possible_keys if key in dictionary]
        if len(matches) == 1:
            key = matches[0]
        elif len(matches) == 0:
            raise PipelineConfigurationError(f"No valid keys were found in the configuration. Please ensure that your top level key is one of: {possible_keys}.")
        else:
            warnings.warn(f"Multiple configuration keys were found, defaulting to the first option: {matches[0]}", PipelineConfigurationWarning)
            key = matches[0]

        return key


    @staticmethod
    def _normalize_pipeline_payload(pipeline_payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        Normalize supported aliases in the pipeline section before model construction.

        Recognized aliases:

        - ``working_dir`` → ``work_dir`` (only when ``work_dir`` is absent).
        - ``stage_to_run`` → ``stages_to_run`` (only when ``stages_to_run`` is absent).

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
        if "stage_to_run" in normalized_payload:
            if "stages_to_run" not in normalized_payload:
                normalized_payload["stages_to_run"] = normalized_payload.pop("stage_to_run")
            else:
                warnings.warn(
                    "Both 'stage_to_run' and 'stages_to_run' were found in the pipeline configuration. "
                    "'stages_to_run' will be used and 'stage_to_run' will be ignored.",
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

    @staticmethod
    def _check_stage_configs(stages: list[Stage], stage_configs: Mapping[str, StageConfig]) -> None:
        """
        Check that all stages have a corresponding stage configuration.

        Warns
        ------
        ``StageConfigurationWarning``
            If any stage does not have a corresponding stage configuration. Handled in one warning instance for all stages without a configuration.
        """
        stage_no_config = []
        for stage in stages:
            if stage.name not in stage_configs:
                stage_no_config.append(stage.name)
        if stage_no_config:
            warnings.warn(
                f"Stage(s) {', '.join(stage_no_config)} added to Pipeline without a corresponding StageConfig. ",
                StageConfigurationWarning,
            )