
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, TYPE_CHECKING, Union

from .errors import StageConfigurationError

if TYPE_CHECKING:
    from .execution import ExecutionContext, StageExecutor
    from .models import StageResult


def _normalize_dependencies(dependencies: Iterable[str] | str | None) -> tuple[str, ...]:
    if dependencies is None:
        return ()

    if isinstance(dependencies, str):
        candidate_items = [dependencies]
    else:
        candidate_items = list(dependencies)

    normalized: list[str] = []
    for dependency in candidate_items:
        dependency_name = str(dependency).strip()
        if dependency_name and dependency_name not in normalized:
            normalized.append(dependency_name)

    return tuple(normalized)


@dataclass
class Stage:
    name: str
    source: Union[Path, Callable[..., Any], None] = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    entrypoint: Optional[str] = None
    backend: str = "python"

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise StageConfigurationError("Stage name cannot be empty.")

        if isinstance(self.source, str):
            self.source = Path(self.source).expanduser()
        elif isinstance(self.source, Path):
            self.source = self.source.expanduser()
        elif self.source is not None and not callable(self.source):
            raise StageConfigurationError("Stage source must be a path, callable, or None.")

        self.dependencies = _normalize_dependencies(self.dependencies)
        self.metadata = dict(self.metadata or {})
        self.backend = str(self.backend or "python").strip() or "python"

    @classmethod
    def from_file(
        cls,
        file_path: str | Path,
        *,
        name: str | None = None,
        dependencies: Iterable[str] | str | None = None,
        metadata: Mapping[str, Any] | None = None,
        entrypoint: str | None = None,
        backend: str = "python",
    ) -> "Stage":
        path = Path(file_path).expanduser()
        if not path.exists():
            raise StageConfigurationError(f"Stage source file does not exist: {path}")

        return cls(
            name=name or path.stem,
            source=path.resolve(),
            dependencies=_normalize_dependencies(dependencies),
            metadata=dict(metadata or {}),
            entrypoint=entrypoint,
            backend=backend,
        )

    @classmethod
    def from_callable(
        cls,
        callable_object: Callable[..., Any],
        *,
        name: str | None = None,
        dependencies: Iterable[str] | str | None = None,
        metadata: Mapping[str, Any] | None = None,
        backend: str = "python",
    ) -> "Stage":
        stage_name = name or getattr(callable_object, "__name__", "stage")
        return cls(
            name=stage_name,
            source=callable_object,
            dependencies=_normalize_dependencies(dependencies),
            metadata=dict(metadata or {}),
            backend=backend,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Stage":
        payload = dict(data)

        source = payload.pop("source", payload.pop("path", None))
        callable_source = payload.pop("callable", None)
        dependencies = payload.pop("dependencies", ())
        metadata = payload.pop("metadata", {})
        entrypoint = payload.pop("entrypoint", None)
        backend = payload.pop("backend", "python")
        name = payload.pop("name", None)

        if callable(source):
            return cls.from_callable(
                source,
                name=name,
                dependencies=dependencies,
                metadata=metadata,
                backend=backend,
            )

        if callable(callable_source):
            return cls.from_callable(
                callable_source,
                name=name,
                dependencies=dependencies,
                metadata=metadata,
                backend=backend,
            )

        if source is not None:
            return cls.from_file(
                source,
                name=name,
                dependencies=dependencies,
                metadata=metadata,
                entrypoint=entrypoint,
                backend=backend,
            )

        raise StageConfigurationError("Stage dictionary must define a source, path, or callable.")

    def with_dependencies(self, *dependencies: str) -> "Stage":
        return replace(
            self,
            dependencies=self.dependencies + _normalize_dependencies(dependencies),
        )

    def validate(self) -> None:
        if self.source is None:
            raise StageConfigurationError(f"Stage '{self.name}' does not define a source.")

        if isinstance(self.source, Path) and not self.source.is_file():
            raise StageConfigurationError(f"Stage source does not exist: {self.source}")

    @property
    def source_path(self) -> Optional[Path]:
        if isinstance(self.source, Path):
            return self.source
        return None

    @property
    def source_label(self) -> Optional[str]:
        if callable(self.source):
            return f"{getattr(self.source, '__module__', '<callable>')}.{getattr(self.source, '__name__', self.name)}"

        if isinstance(self.source, Path):
            return str(self.source)

        return None

    def run(self, context: "ExecutionContext", executor: "StageExecutor") -> "StageResult":
        self.validate()
        return executor.execute(self, context)