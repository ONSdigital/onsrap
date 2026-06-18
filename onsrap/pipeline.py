import os
import time
import json
import hashlib

from dataclasses import dataclass
from datetime import datetime
from pyspark import SparkSession
from .stage import Stage
from .logger import Logger
from pathlib import Path

class Pipeline:
    def __init__(
            self, 
            name: str = None,
            backend: str = "python",    # Either python or R or maybe Spark depending on the use case
            sparksession: SparkSession = None,
            config: dict | str | Path = None, 
            stages: Stage | list[Stage] | list[Pipeline] | list[Stage, Pipeline] = None, 
            logger: Logger = None
            ):
        self.name = name
        self.id = self._create_runtime_id()
        self.backend = backend
        self.sparksession = sparksession
        self.config = config if config is not None else self._construct_default_config()
        self.stages = stages if stages is not None else []
        self.logger = logger if logger is not None else Logger()
        self.manifest = self._construct_manifest()

        self.logger.event("Pipeline initialized", name=self.name, backend=self.backend, id=self.id.get_id())

    def init_stages(self):
        for stage in self.stages:
            self.stages.append(Stage(stage))

        self.logger.event("Stages initialized", stages=[stage.name for stage in self.stages])

    def add_stage(self, *stages: Stage | Pipeline):
        for stage in stages:
            self.stages.append(stage)
        self.logger.event("Stage added", stages=[stage.name for stage in stages])

    def run(self):
        self.validate()
        self.logger.event("Pipeline started", name=self.name, config=self.config)
        
        for stage in self.stages:
            self.logger.event("Executing stage", name=stage.name)
        self.logger.event("Pipeline completed", name=self.name)

    def validate(self):
        self.logger.event("Validating pipeline", name=self.name)
        # Validation logic

    def _construct_manifest(self) -> RunManifest:
        # Construct a manifest based on the pipeline's configuration and stages
        pass

    def _construct_default_config(self) -> RAPConfig:
        # Construct a default config based on the pipeline's stages and other parameters
        return RAPConfig()
    
    def _create_runtime_id(self) -> str:
        # Create a unique runtime ID for this pipeline execution
        now = datetime.now()
        hash = hashlib.sha256(f"{self.name}_{now}".encode()).hexdigest()
        short_hash = hash[:8]
        return RuntimeID(id=f"{now.strftime('%Y-%m-%d_%H%M')}_{short_hash}", timestamp=now, hash=hash, short_hash=short_hash)

    @classmethod
    def from_dict(cls, cfg: dict) -> Pipeline:
        return cls(
            name = cfg.get("name"),
            backend = cfg.get("backend", "python"),
            stages = cfg.get("stages", [])      # And so on for all other class args to exhaustion
        )

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
    log_dir: str = "logs/"
    data_dir: str = "data/"

class RAPDataset:
    def __init__(self):
        self.name = "RAPDataset"

class Logger:
    def __call__(self, *args, **kwds):
        print(*args, **kwds)

    def event(self, event_name: str, **kwargs):
        # Log the event at this Pipeline's logging location with the provided details
        pass

@dataclass
class RunManifest:
    rap_name: str
    run_id: str
    git_commit: str
    stages_run: list[str]
    parameters: dict
    inputs: dict
    outputs: dict
    backend: str
    package_versions: list[str] | str
    timestamp: str
    reason: str | None
    user: str | None

@dataclass
class RAPConfig:
    contents: dict

@dataclass
class Catalog:
    name: str
    description: str
    contents: dict
