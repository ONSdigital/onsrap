from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Union


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
class RAPConfig:
    """
    Holds information on how the Reproducible Analytical Pipeline is 
    configured. 

    Parameters
    ----------
    ``contents`` : dict[str, Any]
        Contains a dictionary of string keys to Any value pairs containing 
        information needed to run the Pipeline.
    """
    contents: dict[str, Any] = field(default_factory=dict)


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
    backend: str = "python"
    work_dir: Path = field(default_factory=Path.cwd)
    project_root: Optional[Path] = None
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    data_dir: Path = field(default_factory=lambda: Path("data"))
    allow_subprocess_fallback: bool = True
    python_executable: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_any(
        cls,
        value: Union["PipelineConfig", RAPConfig, Mapping[str, Any], str, Path, None],
    ) -> "PipelineConfig":
        """
        Converts one of several datatypes into a PipelineConfig class instance. 

        Parameters
        ----------
        ``value`` : PipelineConfig", RAPConfig, Mapping[str, Any], str, Path, None
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

        if isinstance(value, RAPConfig):
            return cls.from_mapping(value.contents)

        if isinstance(value, Mapping):
            return cls.from_mapping(dict(value))

        if isinstance(value, (str, Path)):
            return cls.from_file(Path(value))

        raise TypeError("Unsupported pipeline config type: {0!r}".format(type(value)))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PipelineConfig":
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
        work_dir = Path(payload.pop("work_dir", Path.cwd()))
        project_root_value = payload.pop("project_root", None)
        project_root = Path(project_root_value) if project_root_value is not None else work_dir
        log_dir = Path(payload.pop("log_dir", "logs"))
        data_dir = Path(payload.pop("data_dir", "data"))
        allow_subprocess_fallback = bool(payload.pop("allow_subprocess_fallback", True))
        python_executable = payload.pop("python_executable", None)

        metadata.update(payload)

        return cls(
            name=name,
            backend=backend,
            work_dir=work_dir,
            project_root=project_root,
            log_dir=log_dir,
            data_dir=data_dir,
            allow_subprocess_fallback=allow_subprocess_fallback,
            python_executable=python_executable,
            metadata=metadata,
        )

    @classmethod
    def from_file(cls, path: Path) -> "PipelineConfig":
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
        Converts attributes regarding how the pipeline runs into a dictionary and holds it in
        the ``metadata`` attribute of the ``PipelineConfig`` class. 
        """
        data = {
            "name": self.name,
            "backend": self.backend,
            "work_dir": str(self.work_dir),
            "project_root": str(self.project_root) if self.project_root is not None else None,
            "log_dir": str(self.log_dir),
            "data_dir": str(self.data_dir),
            "allow_subprocess_fallback": self.allow_subprocess_fallback,
            "python_executable": self.python_executable,
        }
        data.update(self.metadata)
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
