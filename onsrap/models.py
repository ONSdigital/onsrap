from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Union


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RuntimeID:
    id: str
    timestamp: datetime
    hash: str
    short_hash: str

    def get_id(self) -> str:
        return self.id

    def get_timestamp(self) -> datetime:
        return self.timestamp

    def get_hash(self) -> str:
        return self.hash

    def get_short_hash(self) -> str:
        return self.short_hash


@dataclass
class RAPConfig:
    contents: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    name: Optional[str] = None
    backend: str = "python"
    work_dir: Path = field(default_factory=Path.cwd)
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
        payload = dict(data)

        metadata = payload.pop("metadata", {})
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
        else:
            metadata = {"metadata": metadata}

        name = payload.pop("name", None)
        backend = payload.pop("backend", "python")
        work_dir = Path(payload.pop("work_dir", Path.cwd()))
        log_dir = Path(payload.pop("log_dir", "logs"))
        data_dir = Path(payload.pop("data_dir", "data"))
        allow_subprocess_fallback = bool(payload.pop("allow_subprocess_fallback", True))
        python_executable = payload.pop("python_executable", None)

        metadata.update(payload)

        return cls(
            name=name,
            backend=backend,
            work_dir=work_dir,
            log_dir=log_dir,
            data_dir=data_dir,
            allow_subprocess_fallback=allow_subprocess_fallback,
            python_executable=python_executable,
            metadata=metadata,
        )

    @classmethod
    def from_file(cls, path: Path) -> "PipelineConfig":
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
        data = {
            "name": self.name,
            "backend": self.backend,
            "work_dir": str(self.work_dir),
            "log_dir": str(self.log_dir),
            "data_dir": str(self.data_dir),
            "allow_subprocess_fallback": self.allow_subprocess_fallback,
            "python_executable": self.python_executable,
        }
        data.update(self.metadata)
        return data


@dataclass
class RunManifest:
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
        return self.status == StageStatus.SUCCEEDED

    @property
    def duration_seconds(self) -> float:
        return max((self.finished_at - self.started_at).total_seconds(), 0.0)


@dataclass
class PipelineRun:
    manifest: RunManifest
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime
    stage_results: list[StageResult] = field(default_factory=list)
    stage_outputs: dict[str, Any] = field(default_factory=dict)

    def result_for(self, stage_name: str) -> Optional[StageResult]:
        for result in self.stage_results:
            if result.name == stage_name:
                return result
        return None

    @property
    def succeeded(self) -> bool:
        return self.status == PipelineStatus.SUCCEEDED
