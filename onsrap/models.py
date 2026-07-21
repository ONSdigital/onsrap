from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

from .errors import StageConfigurationError, PipelineConfigurationError


class StageStatus(str, Enum):
    """
    Class to hold information on how the Stage has run.
    """
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    """
    Class to hold information on how the Pipeline has run.
    """
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def now() -> datetime:
    """
    Function to extract the current time in a datetime format.
    """
    return datetime.now()


def utcnow() -> datetime:
    """
    Function to extract the current time in UTC in a datetime format.
    """
    return now()


@dataclass
class RuntimeID:
    """
    Holds information regarding individual runs. 

    Parameters
    ----------
    ``id`` : str
        The id number for the run.
    ``timestamp`` : datetime
        The time that the run started.
    ``hash`` : str
        A hashed identifier created with the combined ID and
        timestamp to create a unique identifier for the run.
    ``short_hash`` : str
        A shortened version of the ``hash`` attribute to be used 
        in file names for the runs. 
    """
    id: str
    timestamp: datetime
    hash: str
    short_hash: str

    def get_id(self) -> str:
        """
        Getter function to extract the ``id`` attribute.
        """
        return self.id

    def get_timestamp(self) -> datetime:
        """
        Getter function to extract the ``timestamp`` attribute.
        """
        return self.timestamp

    def get_hash(self) -> str:
        """
        Getter function to extract the ``hash`` attribute.
        """
        return self.hash

    def get_short_hash(self) -> str:
        """
        Getter function to extract the ``short_hash`` attribute.
        """
        return self.short_hash


@dataclass
class PipelineConfig:
    """
    Holds information required to run the whole pipeline. 

    Parameters
    ----------
    ``name`` : str, optional
        The name of the pipeline.

        
    ``backend`` : str, default = "python"
        The system that the pipeline is run on. 
    ``work_dir`` : Path 
        The directory to run the Pipeline in. 
    ``project_root`` : Path
        The top level directory for the whole project. 
    ``log_dir`` : Path
        The directory to store the logs in. 
    ``data_dir`` : Path
        The directory where the data is stored. 
    ``output_dir`` : Path, optional
        The directory where pipeline outputs should be written. Not used internally
        by the runner; exposed for stage code to read via ``context.config.output_dir``.
    ``allow_subprocess_fallback`` : bool
        Indicates whether the subprocess system (running the whole file
        rather than an entrypoint function) should be allowed.
    ``python_executable`` : str, optional
        The name of the executable function for the entrypoint of the 
        pipeline. 
    ``metadata`` : dict[str, Any]
        Any additional information on the pipeline. 
    """
    name: Optional[str] = None
    stages_to_run: Optional[dict[str, bool]] = None
    backend: str = "python"
    work_dir: Path = field(default_factory=Path.cwd)
    project_root: Optional[Path] = None
    output_dir: Optional[Path] = None
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    data_dir: Path = field(default_factory=lambda: Path("data"))
    allow_subprocess_fallback: bool = True
    python_executable: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Post-initialization method to ensure that the ``work_dir`` and ``project_root``
        attributes are set correctly. 
        """
        if self.stages_to_run is None:
            self.stages_to_run = {}

    @classmethod
    def from_any(
        cls,
        value: Union[PipelineConfig, Mapping[str, Any], str, Path, None],
    ) -> PipelineConfig:
        """
        Converts one of several datatypes into a PipelineConfig class instance. 

        Parameters
        ----------
        ``value`` : PipelineConfig, Mapping[str, Any], str, Path, or None
            The object holding metadata on how the Pipeline should run to be converted 
            into a PipelineConfig class instance. 
        
        Raises
        ------
        ``TypeError``
            If the datatype for the object holding information on how the pipeline is run
            is not a datatype that can be converted to a PipelineConfig. 
        """
        if value is None:
            return cls()

        if isinstance(value, cls):
            return value

        if isinstance(value, Mapping):
            return cls.from_mapping(dict(value))

        if isinstance(value, (str, Path)):
            return cls.from_file(Path(value))

        raise TypeError("Unsupported pipeline config type: {0!r}".format(type(value)))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> PipelineConfig:
        """
        Extracts information from a mapping datatype and returns a PipelineConfig 
        instance. 

        Parameters
        ----------
        ``data`` : Mapping[str, Any]
            The information to be converted into a ``PipelineConfig`` instance.
        
        Returns
        -------
        ``PipelineConfig`` class instance
        """
        payload = dict(data)

        metadata = payload.pop("metadata", {})
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {"metadata": metadata}

        name = payload.pop("name", None)
        
        backend = payload.pop("backend", "python")
        stages_to_run = PipelineConfig._extract_stages_run(payload)
        work_dir = Path(payload.pop("work_dir", Path.cwd()))
        project_root_value = payload.pop("project_root", None)
        output_dir_value = payload.pop("output_dir", None)
        project_root = Path(project_root_value) if project_root_value is not None else work_dir
        log_dir = Path(payload.pop("log_dir", "logs"))
        data_dir = Path(payload.pop("data_dir", "data"))
        raw_subprocess_fallback = payload.pop("allow_subprocess_fallback", True)
        if isinstance(raw_subprocess_fallback, str):
            warnings.warn(
                "allow_subprocess_fallback should be a boolean, not a string. "
                f"Received {raw_subprocess_fallback!r}. Use an unquoted YAML boolean.",
                UserWarning,
                stacklevel=2,
            )
            allow_subprocess_fallback = raw_subprocess_fallback.strip().lower() not in ("false", "0", "no", "off")
        else:
            allow_subprocess_fallback = bool(raw_subprocess_fallback)
        python_executable = payload.pop("python_executable", None)

        metadata.update(payload)

        return cls(
            name=name,
            stages_to_run = stages_to_run, 
            backend=backend,
            work_dir=work_dir,
            project_root=project_root,
            output_dir=output_dir_value,
            log_dir=log_dir,
            data_dir=data_dir,
            allow_subprocess_fallback=allow_subprocess_fallback,
            python_executable=python_executable,
            metadata=metadata,
        )
    
    @classmethod
    def from_file(cls, path: Path) -> PipelineConfig:
        """
        Extracts a mapping item from a file containing information about how the 
        pipeline should run. 

        Then calls the from_mapping() method to extract the information. 

        Parameters
        ----------
        ``path`` : Path
            The file path containing information to be converted into a PipelineConfig 
            instance. 
        
        Returns
        -------
        ``PipelineConfig`` class instance.

        Raises 
        ------
        ``FileNotFoundError``
            If the file path does not exist.
        ``TypeError`` 
            If the file containing information about how the Pipeline runs does not 
            contain a mapping type.
        """
        config_path = Path(path).expanduser()
        if not config_path.exists():
            raise FileNotFoundError("Config file does not exist: {0}".format(config_path))

        import yaml

        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if raw_config is None:
            return cls()

        if not isinstance(raw_config, Mapping):
            raise TypeError("Pipeline config file must contain a mapping at the top level.")

        return cls.from_mapping(raw_config)

    def to_dict(self) -> dict[str, Any]:
        """
        Returns a prescriptive expression of the attributes within the PipelineConfig instance
        that allows for easier processing by the user. 
        """
        data = {
            "name": self.name,
            "backend": self.backend,
            "work_dir": str(self.work_dir),
            "project_root": str(self.project_root) if self.project_root is not None else None,
            "output_dir": str(self.output_dir) if self.output_dir is not None else None,
            "log_dir": str(self.log_dir),
            "data_dir": str(self.data_dir),
            "output_dir": str(self.output_dir) if self.output_dir is not None else None,
            "allow_subprocess_fallback": self.allow_subprocess_fallback,
            "python_executable": self.python_executable,
        }
        data.update(self.metadata)
        return data
    
    @staticmethod
    def _extract_stages_run(payload: Mapping[str, Any]
                            ) -> dict[str, bool] | None:
        """
        Method to extract stages_to_run configuration and convert all values to boolean values. 

        Parameters
        ----------
        ``payload`` : Mapping[str, Any]
            The dictionary where the stages_to_run configuration is being extracted from.

        Returns 
        -------
        ``boolean_dict``
            A dictionary of stage_name:bool to indicate whether a stage is being run. 
        
        None 
            If stages_to_run does not exist within the configuration.
        """
        stages_to_run = payload.pop("stages_to_run", None)
        if stages_to_run is None: 
            return None
        
        boolean_dict = {stage_name: PipelineConfig._to_bool(value) for stage_name,value in stages_to_run}
        return boolean_dict

    @staticmethod
    def _to_bool(value):
        """
        Method to convert values to boolean True/False values. 

        Integers convert to boolean where 0 = False and 1 = True. A certain subset of strings are
        accepted for conversion. Any other strings will. raise an error.  

        Parameters
        ----------
        ``value`` : bool | int | str

        Returns 
        -------
        ``value``
            The value input but converted to a boolean value. 

        Raises 
        ------
        ``ValueError`` 
            When the value has not been able to be converted to a boolean. 
        """
     
        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return bool(value)

        if isinstance(value, str):
            value = value.strip().lower()

            if value in {"true", "yes", "y", "1"}:
                return True

            if value in {"false", "no", "n", "0"}:
                return False
            
            raise ValueError(f"Cannot convert {value!r} to bool")

        raise ValueError(f"Cannot convert {value!r} to bool")




@dataclass
class StageConfig:
    """
    Holds configuration that should be exposed to an individual stage at runtime.

    Parameters
    ----------
    ``name`` : str
        The name of the stage that this configuration applies to.
    ``_variables`` : dict[str, Any]
        Arbitrary stage-scoped variables.
    ``datasets`` : dict[str, Any]
        Optional dataset-related metadata for the stage.
    ``metadata`` : dict[str, Any]
        Additional supporting metadata for the stage configuration.
    """
    name: str
    _variables: dict[str, Any] = field(default_factory=dict)
    datasets: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, Any] | None = None) -> StageConfig:
        """
        Build a ``StageConfig`` from a mapping loaded from code or configuration files.

        The ``datasets`` and ``metadata`` keys are extracted into their dedicated
        attributes. All remaining keys are treated as stage variables that should be
        exposed to the stage at runtime.

        Parameters
        ----------
        ``name`` : str
            Stage name that this configuration applies to.
        ``data`` : Mapping[str, Any] or None
            Raw configuration payload for that stage.

        Returns
        -------
        ``StageConfig``
            A normalized stage configuration object.
        """
        payload = dict(data or {})

        datasets = payload.pop("datasets", {})
        if isinstance(datasets, Mapping):
            datasets = dict(datasets)
        else:
            raise StageConfigurationError("Stage datasets must be provided as a mapping.")

        metadata = payload.pop("metadata", {})
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {"metadata": metadata}

        return cls(
            name=str(name).strip(),
            _variables=payload,
            datasets=datasets,
            metadata=metadata,
        )

    @property
    def variables(self) -> dict[str, Any]:
        """
        Return a copy of the stage variables without datasets or metadata.
        """
        return dict(self._variables)

    def get(self, variable: str, default: Any = None) -> Any:
        """
        Return a configured variable if present, otherwise return ``default``.
        """
        return self._variables.get(variable, default)

    def require(self, variable: str) -> Any:
        """
        Return a configured variable and raise if the stage does not define it.
        """
        if variable not in self._variables:
            raise StageConfigurationError(
                f"Stage configuration '{self.name}' does not define '{variable}'."
            )
        return self._variables[variable]

    def get_variables(self, variable: Iterable[str] | str | None = None) -> Any:
        """
        Return all configured variables, one configured variable, or a selected subset.
        """
        if variable is None:
            return dict(self._variables)

        if isinstance(variable, str):
            return self.require(variable)

        requested_variables: dict[str, Any] = {}
        missing_variables: list[str] = []
        for requested_name in variable:
            if requested_name in self._variables:
                requested_variables[requested_name] = self._variables[requested_name]
            else:
                missing_variables.append(requested_name)

        if missing_variables:
            missing = ", ".join(sorted(missing_variables))
            raise StageConfigurationError(
                f"Stage configuration '{self.name}' does not define: {missing}."
            )

        return requested_variables

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the stage configuration back to a mapping suitable for manifests.
        """
        data = dict(self._variables)
        if self.datasets:
            data["datasets"] = dict(self.datasets)
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data


@dataclass
class RunManifest:
    """
    Holds metadata information about the run. 

    Parameters
    ----------
    ``rap_name`` : str, default = ""
        The name of the Pipeline.
    ``run_id`` : str, default = ""
        The unique ID of the run. 
    ``git_commit`` : str, default = None
        The git commit number for the run, indicating the exact state of the code.
    ``stages_run`` : list[str]
        List of the names of stages that were included in this run. 
    ``parameters`` : dict[str, Any]

    ``inputs`` : dict[str, Any]

    ``outputs`` : dict[str, Any]

    ``backend`` : str, default = "python"
        The system that the Pipeline will run in. 
    ``package_versions``: list[str] or str
        The package versions that are used in this run. 
    ``timestamp`` : str, default = ""
        The time that this run started.
    ``reason`` : str, optional, default = None
        The reason that this run took place. 
    ``user`` : str, optional, default = None
        The person running this specific run. 
    """
    rap_name: str = ""
    run_id: str = ""
    git_commit: Optional[str] = None
    stages_run: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    backend: str = "python"
    package_versions: Union[list[str], str] = field(default_factory=list)
    timestamp: str = ""
    reason: Optional[str] = None
    user: Optional[str] = None


class RAPDataset:
    def __init__(self):
        self.name = "RAPDataset"


@dataclass
class Catalog:
    name: str
    description: str
    contents: dict[str, Any]


@dataclass
class StageResult:
    """
    Holds information about how the stage ran.

    Parameters
    ----------
    ``name`` : str
        The name of the Stage run. 
    ``status`` : StageStatus
        The status of the run at completion. 
    ``started_at`` : datetime
        The date and time that the Stage started. 
    ``finished_at`` : datetime
        The date and time that the Stage finished. 
    ``outputs`` : Any, default = None
        Captures outputs of the stage being run.
    ``stdout`` : str, default = ""
        Captures outputs of the stage being run.
    ``stderr`` : str, default = ""
        Captures any errors produced during the run. 
    ``return_code`` : int, optional, default = None
        Indicates whether the stage has run successfully or if there
        was an error. 
    ``metadata``: dict[str, Any]
        Holds information about the Stage such as file directories. 
    ``error`` : str, optional, default = None
        Any errors produced during the run. 
    ``source`` : str, optional, default = None
        The name/location of the code for that Stage run. 
    """
    name: str
    status: StageStatus
    started_at: datetime
    finished_at: datetime
    outputs: Any = None
    stdout: str = ""
    stderr: str = ""
    return_code: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    source: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        """
        Creates a new attribute in the ``StageResult`` class called ``succeeded`` that 
        contains a boolean value indicating if the run was a success or not. 
        Updates the ``status`` attribute to record that the Stage ran successfully. 
        """
        return self.status == StageStatus.SUCCEEDED

    @property
    def duration_seconds(self) -> float:
        """
        Creates a new attribute in the ``StageResult`` class called ``duration_seconds``
        that holds the exact duration of the stage in seconds. 
        """
        return max((self.finished_at - self.started_at).total_seconds(), 0.0)


@dataclass
class PipelineRun:
    """
    Holds information about how the whole Pipeline ran. 

    Parameters
    ----------
    ``manifest`` : RunManifest class instance
        Metadata on how the specific run has gone.
    ``status`` : PipelineStatus class instance
        Whether the Pipeline ran successfully or if there were errors.
    ``started_at`` : datetime
        The date and time the Pipeline started. 
    ``completed_at`` : datetime
        The date and time the Pipeline ended. 
    ``stage_results`` : list[StageResult]
        Holds the results for every stage run as part of the Pipeline. 
    ``stage_outputs`` : dict[str, Any]
        Holds the outputs from all stages run as part of the Pipeline. 
    """
    manifest: RunManifest
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime
    stage_results: list[StageResult] = field(default_factory=list)
    stage_outputs: dict[str, Any] = field(default_factory=dict)

    def result_for(self, stage_name: str) -> Optional[StageResult]:
        """
        Extracts the results for a specific stage. 
        
        Parameters
        ----------
        ``stage_name`` : str
            The name of the Stage that you are requesting the results for. 
        """
        for result in self.stage_results:
            if result.name == stage_name:
                return result
        return None

    @property
    def succeeded(self) -> bool:
        """
        Creates a new attribute in the ``PipelineRun`` class called ``succeeded`` that 
        contains a boolean value indicating if the Pipeline was a success or not. 
        Updates the ``status`` attribute to record that the Pipeline ran successfully. 
        """
        return self.status == PipelineStatus.SUCCEEDED
