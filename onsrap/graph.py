from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .errors import DependencyCycleError, DuplicateStageError, MissingDependencyError
from .stage import Stage


@dataclass
class StageGraph:
    stages: list[Stage] = field(default_factory=list)

    @classmethod
    def from_stages(cls, stages: Iterable[Stage]) -> "StageGraph":
        return cls(list(stages))

    def validate(self) -> None:
        names = [stage.name for stage in self.stages]
        seen = set()
        duplicates = []
        for name in names:
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)

        if duplicates:
            raise DuplicateStageError(
                "Duplicate stage names are not allowed: {0}".format(
                    ", ".join(sorted(duplicates))
                )
            )

        stage_names = set(names)
        missing = []
        for stage in self.stages:
            for dependency in stage.dependencies:
                if dependency not in stage_names:
                    missing.append("{0} -> {1}".format(stage.name, dependency))

        if missing:
            raise MissingDependencyError(
                "Unknown stage dependencies: {0}".format(", ".join(missing))
            )

        self.topological_order()

    def topological_order(self) -> list[Stage]:
        stage_by_name = {stage.name: stage for stage in self.stages}
        incoming = {stage.name: set(stage.dependencies) for stage in self.stages}
        dependents = {stage.name: set() for stage in self.stages}

        for stage in self.stages:
            for dependency in stage.dependencies:
                dependents[dependency].add(stage.name)

        original_order = [stage.name for stage in self.stages]
        ready = [name for name in original_order if not incoming[name]]
        ordered = []

        while ready:
            current = ready.pop(0)
            ordered.append(current)

            for dependent in dependents[current]:
                incoming[dependent].discard(current)

            for name in original_order:
                if name in ordered or name in ready:
                    continue
                if not incoming[name]:
                    ready.append(name)

        if len(ordered) != len(self.stages):
            unresolved = [name for name in original_order if name not in ordered]
            raise DependencyCycleError(
                "Stage graph contains a cycle or unresolved dependencies: {0}".format(
                    ", ".join(unresolved)
                )
            )

        return [stage_by_name[name] for name in ordered]
