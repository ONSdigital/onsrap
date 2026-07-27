from __future__ import annotations

from textwrap import indent
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

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
    ``stages_to_run`` : dict[str, bool], optional   
        A dictionary of all stage names alongside a boolean value that indicates 
        whether the stage should be run or not.
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

    def __str__(self) -> str:
        """
        String method that returns a human-readable representation of the ``PipelineConfig`` class.

        Returns
        -------
        str
            A string representation of the ``PipelineConfig`` class with its attributes.
        """
        return (
            f"    Name: {self.name}\n    Stages To Run: {_format_dict(self.stages_to_run, indent=4)}\n"
            f"    Backend: {self.backend} \n"
            f"    Work Directory: {self.work_dir}\n    Project Root: {self.project_root}\n"
            f"    Output Directory: {self.output_dir}\n    Log Directory: {self.log_dir}\n"
            f"    Data Directory: {self.data_dir}\n    Allow Subprocess Fallback: {self.allow_subprocess_fallback}\n"
            f"    Python Executable: {self.python_executable}\n    Metadata: \n{_format_dict(self.metadata, indent=8)}"
        )

    def __repr__(self) -> str:
        """
        Representation method that returns a human readable representation of the ``PipelineConfig`` class. 
        This method is structured to be more concise than the ``__str__`` method and is 
        intended for debugging purposes.

        Returns 
        -------
        str
            A string representation of the ``PipelineConfig`` class with its attributes.
        """
        return (
            f"PipelineConfig(name={self.name}, stages_to_run={self.stages_to_run}, "
            f"backend={self.backend}, "
            f"work_dir={self.work_dir}, project_root={self.project_root}, "
            f"output_dir={self.output_dir}, log_dir={self.log_dir}, data_dir={self.data_dir}, "
            f"allow_subprocess_fallback={self.allow_subprocess_fallback}, "
            f"python_executable={self.python_executable}, metadata={self.metadata})"
        )

    @classmethod
    def from_any(
        cls,
        value: PipelineConfig | Mapping[str, Any] | str | Path | None,
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
        
        boolean_dict = {
            stage_name: PipelineConfig._to_bool(value) 
            for stage_name, value in stages_to_run.items()
            }
        
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
    ``metadata`` : dict[str, Any]
        Additional supporting metadata for the stage configuration.
    """
    # TODO: output location for stages potentially problematic for output overwrites!
    name: str
    _variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, name: str, data: Mapping[str, Any] | None = None, global_vars: Mapping[str, Any] | None = None) -> StageConfig:
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
        ``global_vars`` : Mapping[str, Any] or None
            Global variables from config file that need to be parsed to every stage.

        Returns
        -------
        ``StageConfig``
            A normalized stage configuration object.
        """
        payload = dict(data or {})

        metadata = payload.pop("metadata", {})
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {"metadata": metadata}

        return cls(
            name=str(name).strip(),
            _variables=payload,
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
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

@dataclass
class GlobalConfig:
    """
    Holds configuration that should be exposed to all stages at runtime.

    Parameters
    ----------
    ``_variables`` : dict[str, Any]
        Variables that should be parsed to all stages throughout the pipeline.
    """
    _variables: dict[str, Any] = field(default_factory=dict)
    exclusion: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], exclusions: dict[str, Any] | None = None) -> GlobalConfig:
        """
        Build a ``GlobalConfig`` from a mapping loaded from code or configuration files.

        Parameters
        ----------
        ``data`` : Mapping[str, Any]
            Raw configuration payload for the global configuration.
        ``exclusions`` : dict[str, Any] or None
            A lookup of which global variables should be excluded from each stage. 

        Returns
        -------
        ``GlobalConfig``
            A global configuration object.
        """
        payload = dict(data or {})
        
        return cls(_variables=payload, 
                   exclusion=exclusions)

    def get_attributes(self, keep_exclusion: bool = True) -> dict[str, Any]:
        """
        Return a copy of the global variables, optionally excluding any variables
        specified in the exclusion list.

        Parameters
        ----------
        ``keep_exclusion`` : bool, default = True
            If True, return both _variables and exclusion.
            If False, return only the variables and not the exclusion list.

        Returns
        -------
        ``self._variables`` : dict[str, Any]
            All global variables for the pipeline.
        ``self.exclusion`` : dict[str, Any]
            The exclusion list of global variables for each stage. Only returned 
            if ``keep_exclusion`` is True.
        """
        if keep_exclusion: 
            return self._variables, self.exclusion
        else:
            return self._variables


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
    package_versions: list[str] | str = field(default_factory=list)
    timestamp: str = ""
    reason: Optional[str] = None
    user: Optional[str] = None

    def __str__(self) -> str:
        """
        String method that returns a human-readable representation of the ``RunManifest``
        class.

        Returns
        -------
        str
            A string representation of the ``RunManifest`` class with its attributes.
        """

        return (
            f"\nRAP Name: {self.rap_name}\nRun ID: {self.run_id} \n"
            f"Git Commit: {self.git_commit}\nStages Run: {self.stages_run} \n"
            f"Parameters: \n{_format_dict(self.parameters, indent=4)} \n"
            f"Inputs: \n{_format_dict(self.inputs, indent=4)} \n"
            f"Outputs: \n{_format_dict(self.outputs, indent = 4)} \nBackend: {self.backend} \n"
            f"Package Versions: {self.package_versions} \nTimestamp: {self.timestamp}\n"
            f"Reason: {self.reason} \nUser: {self.user}\n"
        )

    def __repr__(self) -> str:
        """
        Representation method that returns a human readable representation of the 
        ``RunManifest`` class. This method is structured to be more concise than 
        the ``__str__`` method and is intended for debugging purposes.

        Returns 
        -------
        str
            A string representation of the ``RunManifest`` class with its attributes.
        """
        return (
            f"RunManifest(rap_name={self.rap_name}, run_id={self.run_id}, "
            f"git_commit={self.git_commit}, stages_run={self.stages_run}, "
            f"parameters={self.parameters}, inputs={self.inputs}, "
            f"outputs={self.outputs}, backend = {self.backend}, "
            f"package_versions={self.package_versions}, "
            f"timestamp={self.timestamp}, reason={self.reason}, user={self.user})"
        )


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

def _format_dict(d, indent=0):
            lines = []
            for key, value in d.items():
                if isinstance(value, dict):
                    lines.append(f"{' ' * indent}{key}:")
                    lines.append(_format_dict(value, indent + 4))
                else:
                    lines.append(f"{' ' * indent}{key}: {value}")
            return "\n".join(lines)
