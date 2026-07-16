from onsrap.models import StageStatus, PipelineStatus, RuntimeID, RAPConfig, RunManifest, PipelineRun, PipelineConfig
import pytest
import datetime
from pathlib import Path
from textwrap import dedent
from tests.test_execution import stageresult

def test_stagestatus() -> None:
    """
    Test that stagestatus outputs the correct values.
    """
    assert StageStatus.PENDING == "pending"
    assert StageStatus.RUNNING == "running"
    assert StageStatus.SUCCEEDED == "succeeded"
    assert StageStatus.FAILED == "failed"
    assert StageStatus.SKIPPED == "skipped"

def test_pipeline_status() -> None: 
    """
    Test that pipeline status outputs the correct values.
    """
    assert PipelineStatus.PENDING == "pending"
    assert PipelineStatus.RUNNING == "running"
    assert PipelineStatus.SUCCEEDED == "succeeded"
    assert PipelineStatus.FAILED == "failed"

@pytest.fixture
def runtimeID() -> RuntimeID:
    """
    Example RuntimeID instance for testing of other methods. 
    """
    return RuntimeID(id = "abc123",
                     timestamp = datetime.datetime(2026, 7, 7, 13, 5, 46),
                     hash = "fnruw9574893ghkwq234h5kg",
                     short_hash = "4h5kg")

def test_runtimeID_creation(runtimeID) -> None: 
    """
    Test that a RuntimeID is correctly created. 
    """
    assert runtimeID.id == "abc123"
    assert runtimeID.timestamp == datetime.datetime(2026, 7, 7, 13, 5, 46)
    assert runtimeID.hash == "fnruw9574893ghkwq234h5kg"
    assert runtimeID.short_hash == "4h5kg"

def test_getter_functions_runtimeID(runtimeID) -> None:
    """
    Tests all the getter functions for the RuntimeID instance. 
    """
    assert runtimeID.get_id() == "abc123"
    assert runtimeID.get_timestamp() == datetime.datetime(2026, 7, 7, 13, 5, 46)
    assert runtimeID.get_hash() == "fnruw9574893ghkwq234h5kg"
    assert runtimeID.get_short_hash() == "4h5kg"

@pytest.fixture
def rapconfig() -> RAPConfig:
    """
    Example RAPConfig class instance for testing of class methods. 
    """
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
    """
    Blank PipelineConfig instance for class method testing. 
    """
    return PipelineConfig()

@pytest.fixture
def pipelineconfig() -> PipelineConfig:
    """
    Example PipelineConfig completed class instance for method testing. 
    """
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
    """
    Example mapping dictionary for use in testing from_mapping() method. 
    """
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
    """
    Test derivation for a PipelineConfig instance using the from_any() method. This test 
    checks all methods EXCEPT from_file as this will be covered in another test due to 
    creation of a mock file being required. 
    """
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

def test_from_file(tmp_path,) -> PipelineConfig:
    pipeline_config = tmp_path / "configuration.py"
    pipeline_config.write_text(
        dedent(
            """
            {"name":"test_rap",
                             "backend":"python",
                             "work_dir":"tmp/work",
                             "project_root":"project",
                             "log_dir":"tmp/logs",
                             "data_dir":"tmp/data",
                             "allow_subprocess_fallback":True,
                             "python_executable": ,
                             "metadata":{"variables":["name","age"],
                                         "num_stages":6}
                                         }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    no_map_pipeline_config = tmp_path / "not_valid.py"
    no_map_pipeline_config.write_text(
        dedent(
            """
            variable = "Hello world"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    configuration = PipelineConfig.from_file(pipeline_config)
    assert configuration == PipelineConfig(name = "test_rap",
                                            backend = "python",
                                            work_dir = Path("tmp/work"),
                                            project_root = Path("project"),
                                            log_dir = Path("tmp/logs"),
                                            data_dir = Path("tmp/data"),
                                            allow_subprocess_fallback = True,
                                            python_executable = None,
                                            metadata = {"variables":["name","age"],
                                                        "num_stages":6})
    
    fake_file = "path_not_real"
    with pytest.raises(FileNotFoundError):
        PipelineConfig.from_file(fake_file)
    with pytest.raises(TypeError):
        PipelineConfig.from_file(no_map_pipeline_config)

def test_to_dict(pipelineconfig) -> None:
    """
    Test of to_dict() class method for PipelineConfig that it outputs the PipelineConfig values
    as a dictionary. 
    """

    assert pipelineconfig.to_dict() == {"name":"test_rap",
                                        "backend":"python",
                                        "work_dir":"tmp\\work",
                                        "project_root":"project",
                                        "output_dir":None,
                                        "log_dir":"tmp\\logs",
                                        "data_dir":"tmp\\data",
                                        "allow_subprocess_fallback":True,
                                        "python_executable":None,
                                        "variables":["name","age"],
                                         "num_stages":6}
    
    
@pytest.fixture
def runmanifest() -> RunManifest:
    """
    Example RunManifest class instance for testing of class method. 
    """
    return RunManifest("pipeline",
                       "1",
                       None,
                       ["stage1","stage2"],
                       {"uniqueID":"example"},
                       {"input_path":"input/data/example.csv"},
                       {"output_path":"output/data/example.csv"},
                       "python",
                       ["1.3.2"],
                       "",
                       None,
                       None)

def test_stage_result(stageresult) -> None:
    """
    Uses a StageResult instance created in test_execution to ensure that
    the class instance is created suitably with required defaults. 
    """
    assert stageresult.name == "stage_test"
    assert stageresult.status == "pending"
    assert stageresult.started_at == '2024-05-06 15:45:30'
    assert stageresult.finished_at == '2024-05-07 15:45:30'
    assert stageresult.outputs == "example output"
    assert stageresult.stdout == ""
    assert stageresult.stderr == ""
    assert stageresult.return_code == None
    assert stageresult.metadata == {}
    assert stageresult.error == None
    assert stageresult.source == None

@pytest.mark.parametrize("status_stage,expected_stage",
                         [(StageStatus.PENDING, False),
                          (StageStatus.RUNNING, False),
                          (StageStatus.FAILED, False),
                           (StageStatus.SUCCEEDED, True),
                           (StageStatus.SKIPPED, False)])

def test_succeeded(stageresult, status_stage, expected_stage) -> None: 
    """
    Tests succeeded() method for StageResult which outputs True or False depending on
    the status of the StageResult. 
    """
    stageresult.status = status_stage
    assert stageresult.succeeded == expected_stage

def test_duration_seconds(stageresult) -> None: 
    stageresult.started_at = datetime.datetime(2024,5,6,15,45,30)
    stageresult.finished_at = datetime.datetime(2024,5,7,15,45,30)
    seconds_value = (datetime.datetime(2024,5,7,15,45,30) - datetime.datetime(2024,5,6,15,45,30)).total_seconds()
    assert stageresult.duration_seconds == seconds_value

@pytest.fixture
def pipelinerun(stageresult, runmanifest) -> PipelineRun:
    return PipelineRun(runmanifest,
                       PipelineStatus.SUCCEEDED,
                       datetime.datetime(2024,5,6,15,45,30),
                       datetime.datetime(2024,5,7,15,45,30),
                       [stageresult],
                       {"stage_test":"example output"})

def test_pipelinerun_configuration(pipelinerun, runmanifest, stageresult) -> None: 
    assert pipelinerun.manifest == runmanifest
    assert pipelinerun.status == PipelineStatus.SUCCEEDED
    assert pipelinerun.started_at == datetime.datetime(2024,5,6,15,45,30)
    assert pipelinerun.completed_at == datetime.datetime(2024,5,7,15,45,30)
    assert pipelinerun.stage_results == [stageresult]
    assert pipelinerun.stage_outputs == {"stage_test":"example output"}

def test_result_for(pipelinerun, stageresult) -> None: 
    assert pipelinerun.result_for("stage_test") == stageresult
    assert pipelinerun.result_for("not_a_stage") == None

@pytest.mark.parametrize("status,expected",
                         [(PipelineStatus.PENDING, False),
                          (PipelineStatus.RUNNING, False),
                          (PipelineStatus.FAILED, False),
                           (PipelineStatus.SUCCEEDED, True)])

def test_succeeded_pipeline(pipelinerun, status, expected) -> None: 
    pipelinerun.status = status
    assert pipelinerun.succeeded == expected