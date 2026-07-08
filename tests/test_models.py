from onsrap.models import StageStatus, PipelineStatus, RuntimeID, RAPConfig, RunManifest, StageResult, PipelineRun, PipelineConfig
import pytest
import datetime
from pathlib import Path
from textwrap import dedent

def test_stagestatus() -> None:
    assert StageStatus.PENDING == "pending"
    assert StageStatus.RUNNING == "running"
    assert StageStatus.SUCCEEDED == "succeeded"
    assert StageStatus.FAILED == "failed"
    assert StageStatus.SKIPPED == "skipped"

def test_pipeline_status() -> None: 
    assert PipelineStatus.PENDING == "pending"
    assert PipelineStatus.RUNNING == "running"
    assert PipelineStatus.SUCCEEDED == "succeeded"
    assert PipelineStatus.FAILED == "failed"

@pytest.fixture
def runtimeID() -> RuntimeID:
    return RuntimeID(id = "abc123",
                     timestamp = datetime.datetime(2026, 7, 7, 13, 5, 46),
                     hash = "fnruw9574893ghkwq234h5kg",
                     short_hash = "4h5kg")

def test_runtimeID_creation(runtimeID) -> None: 
    assert runtimeID.id == "abc123"
    assert runtimeID.timestamp == datetime.datetime(2026, 7, 7, 13, 5, 46)
    assert runtimeID.hash == "fnruw9574893ghkwq234h5kg"
    assert runtimeID.short_hash == "4h5kg"

def test_getter_functions_runtimeID(runtimeID) -> None:
    assert runtimeID.get_id() == "abc123"
    assert runtimeID.get_timestamp() == datetime.datetime(2026, 7, 7, 13, 5, 46)
    assert runtimeID.get_hash() == "fnruw9574893ghkwq234h5kg"
    assert runtimeID.get_short_hash() == "4h5kg"

@pytest.fixture
def rapconfig() -> RAPConfig:
    return RAPConfig(contents = {"name":"test_rap",
                                 "backend":"python",
                                 "work_dir":Path("tmp/work"),
                                 "project_root":Path("project"),
                                 "log_dir":Path("tmp/logs"),
                                 "data_dir":Path("tmp/data"),
                                 "allow_subprocess_fallback":True,
                                 "python_executable":None,
                                 "metadata":{"variables":["name","age"],
                                             "num_stages":6}})

@pytest.fixture
def blankpipelineconfig() -> PipelineConfig:
    return PipelineConfig()

@pytest.fixture
def pipelineconfig() -> PipelineConfig:
    return PipelineConfig(name = "test_rap",
                          backend = "python",
                          work_dir = Path("tmp/work"),
                          project_root = Path("project"),
                          log_dir = Path("tmp/logs"),
                          data_dir = Path("tmp/data"),
                          allow_subprocess_fallback = True,
                          python_executable = None,
                          metadata = {"variables":["name","age"],
                                      "num_stages":6})

@pytest.fixture
def mapping() -> dict:
    return {"name":"test_rap",
            "backend":"python",
            "work_dir":Path("tmp/work"),
            "project_root":Path("project"),
            "log_dir":Path("tmp/logs"),
            "data_dir":Path("tmp/data"),
            "allow_subprocess_fallback":True,
            "python_executable":None,
            "metadata":{"variables":["name","age"],
                        "num_stages":6}}


def test_from_any(mapping, pipelineconfig, blankpipelineconfig, rapconfig) -> None: 
    assert blankpipelineconfig.from_any(None) == PipelineConfig()
    assert blankpipelineconfig.from_any(pipelineconfig) == PipelineConfig(name = "test_rap",
                                                                          backend = "python",
                                                                          work_dir = Path("tmp/work"),
                                                                          project_root = Path("project"),
                                                                          log_dir = Path("tmp/logs"),
                                                                          data_dir = Path("tmp/data"),
                                                                          allow_subprocess_fallback = True,
                                                                          python_executable = None,
                                                                          metadata = {"variables":["name","age"],
                                                                                      "num_stages":6})
    assert blankpipelineconfig.from_any(rapconfig) == PipelineConfig(name = "test_rap",
                                                                    backend = "python",
                                                                    work_dir = Path("tmp/work"),
                                                                    project_root = Path("project"),
                                                                    log_dir = Path("tmp/logs"),
                                                                    data_dir = Path("tmp/data"),
                                                                    allow_subprocess_fallback = True,
                                                                    python_executable = None,
                                                                    metadata = {"variables":["name","age"],
                                                                                "num_stages":6})
    assert blankpipelineconfig.from_any(mapping) == PipelineConfig(name = "test_rap",
                                                                    backend = "python",
                                                                    work_dir = Path("tmp/work"),
                                                                    project_root = Path("project"),
                                                                    log_dir = Path("tmp/logs"),
                                                                    data_dir = Path("tmp/data"),
                                                                    allow_subprocess_fallback = True,
                                                                    python_executable = None,
                                                                    metadata = {"variables":["name","age"],
                                                                                "num_stages":6})
    
    with pytest.raises(TypeError):
        blankpipelineconfig.from_any(11)

"""NOT SURE HOW TO TEST FROM_FILE()"""