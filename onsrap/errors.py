from __future__ import annotations


class OnsrapError(Exception):
    """Base exception for onsrap."""


class PipelineValidationError(OnsrapError):
    """Raised when the pipeline definition is invalid."""


class StageConfigurationError(PipelineValidationError):
    """Raised when a stage definition is malformed."""


class DuplicateStageError(PipelineValidationError):
    """Raised when two stages share the same name."""


class MissingDependencyError(PipelineValidationError):
    """Raised when a stage depends on an unknown stage."""


class DependencyCycleError(PipelineValidationError):
    """Raised when the stage graph contains a cycle."""


class StageExecutionError(OnsrapError):
    """Raised when a stage fails during execution."""

    def __init__(
        self,
        message: str,
        stage_name: str | None = None,
        source: str | None = None,
        original_exception: Exception | None = None,
        result: object | None = None,
    ):
        super().__init__(message)
        self.stage_name = stage_name
        self.source = source
        self.original_exception = original_exception
        self.result = result


class StageLoadError(StageExecutionError):
    """Raised when a file-backed stage cannot be loaded."""
