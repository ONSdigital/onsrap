from onsrap.execution import ExecutionContext
from onsrap.models import PipelineConfig, StageResult, StageStatus
from onsrap.logger import Logger
from pathlib import Path
import pytest

@pytest.fixture
def logger() -> Logger:
    """
    Logger instance for testing
    """
    return Logger()

@pytest.fixture
def config() -> PipelineConfig:
    """
    Return a PipelineConfig object for testing.
    """
    work_dir = Path('tmp/work_dir')
    project_root = Path('tmp/project')
    log_dir = Path('tmp/log')
    data_dir = "tmp/config_data"
    return PipelineConfig(
        "test_pipeline",
        "python",
        work_dir, 
        project_root, 
        log_dir, 
        data_dir, 
        True, 
        None,
        {}
    )

@pytest.fixture
def execution(config, logger) -> ExecutionContext:
    """
    Create an ExecutionContext object for testing.
    """
    run_dir = Path("tmp/run")
    work_dir = Path('tmp/work_dir')

    return ExecutionContext(
        "test_pipeline",
        "run_id_1234",
        config, 
        logger,
        run_dir,
        '2024-05-06 15:45:30',
        work_dir,
        {},
        {}        
    )

@pytest.fixture
def stageresult() -> StageResult:
    """
    Test StageResult instance for running ExecutionContext tests.
    """
    return StageResult(
        "stage_test",
        StageStatus.PENDING,
        '2024-05-06 15:45:30',
        '2024-05-07 15:45:30',
        metadata={},
        outputs = "example output"
    )


def test_executioncontext_creation(execution, logger, config) -> None:
    """
    Test that the ExecutionContext creates the right attributes. 
    """ 
    assert execution.pipeline_name == "test_pipeline"
    assert execution.run_id == "run_id_1234"
    assert execution.config == config
    assert execution.logger == logger
    assert execution.run_dir == Path("tmp/run")
    assert execution.started_at == '2024-05-06 15:45:30'
    assert execution.working_directory == Path('tmp/work_dir')
    assert execution.stage_results == {}
    assert execution.variables == {}

def test_record(stageresult, execution) -> None:
    """
    Tests that StageResult attributes are attached to stage_results and variables
    attributes in the ExecutionContext instance. 
    """
    execution.record(stageresult)
    assert execution.stage_results == {'stage_test':StageResult(name='stage_test', 
                                                                status='pending', 
                                                                started_at='2024-05-06 15:45:30', 
                                                                finished_at='2024-05-07 15:45:30', 
                                                                outputs="example output", 
                                                                stdout='', 
                                                                stderr='', 
                                                                return_code=None, 
                                                                metadata={}, 
                                                                error=None, 
                                                                source=None)}
    assert execution.variables == {'stage_test':"example output"}

def test_result_for(execution, stageresult) -> None:
    """
    Tests that result_for correctly extracts the results of a requested stage.
    """
    execution.record(stageresult)
    assert execution.result_for("stage_test") == StageResult(name='stage_test', 
                                                                status='pending', 
                                                                started_at='2024-05-06 15:45:30', 
                                                                finished_at='2024-05-07 15:45:30', 
                                                                outputs="example output", 
                                                                stdout='', 
                                                                stderr='', 
                                                                return_code=None, 
                                                                metadata={}, 
                                                                error=None, 
                                                                source=None)

def test_stage_outputs(execution, stageresult) -> None: 
    """
    Tests that stage_outputs shows the outputs attribute of the StageResult
    instance for a requested stage is extracted.
    """
    execution.record(stageresult)
    assert execution.stage_outputs == {"stage_test":"example output"}

def test_resolve_data_root(execution) -> None: 
    """
    Tests that resolve_data_root method extracts the path from the execution context
    or, if the context is None, returns the file path for the module itself and the 
    data directory within that. 
    """
    assert execution.resolve_data_root(execution.config) == Path("tmp/config_data")
    
    import onsrap.execution as execution_module
    result = execution.resolve_data_root(None)
    expected = (
        Path(execution_module.__file__).resolve().parents[1]
        / "data"
    )
    assert result == expected

