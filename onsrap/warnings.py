from __future__ import annotations

class OnsrapWarning(Warning):
    """Base warning for onsrap."""

class StageConfigurationWarning(OnsrapWarning):
    """
    Raised when the stage configuration is not optimal.
    Child class with ``OnsrapWarning`` as the parent class.
    """

class PipelineConfigurationWarning(OnsrapWarning):
    """
    Raised when the pipeline configuration is not optimal.
    Child class with ``OnsrapWarning`` as the parent class.
    """

class ConfigurationInjectionWarning(OnsrapWarning):
    """
    Raised when the configuration injection is not optimal.
    Child class with ``OnsrapWarning`` as the parent class.
    """