from __future__ import annotations


class OnsrapError(Exception):
    """Base exception for onsrap."""


class PipelineValidationError(OnsrapError):
    """
    Raised when the pipeline definition is invalid.
    Child class with ``OnsrapError`` as the parent class.
    """


class StageConfigurationError(PipelineValidationError):
    """
    Raised when a stage definition is malformed.
    Child class with ``PipelineValidationError`` as the parent class.
    """


class DuplicateStageError(PipelineValidationError):
    """
    Raised when two stages share the same name.
    Child class with ``PipelineValidationError`` as the parent class.
    """


class MissingDependencyError(PipelineValidationError):
    """
    Raised when a stage depends on an unknown stage.
    Child class with ``PipelineValidationError`` as the parent class.
    """


class DependencyCycleError(PipelineValidationError):
    """
    Raised when the stage graph contains a cycle.
    Child class with ``PipelineValidationError`` as the parent class.
    """


class StageExecutionError(OnsrapError):
    """
    Raised when a stage fails during execution.
    Child class with ``OnsrapError`` as the parent class.
    """

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
    """
    Raised when a file-backed stage cannot be loaded.
    Child class with ``StageExecutionError`` as the parent class.
    """

class StageDependencyError(OnsrapError):
    """
    Raised when incorrect inputs are provided to the dependency
    attribute of a Stage.
    """