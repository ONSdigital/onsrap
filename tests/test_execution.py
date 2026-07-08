from onsrap.execution import ExecutionContext, PythonStageExecutor
from onsrap.models import PipelineConfig, StageResult, StageStatus
from onsrap.logger import Logger
from pathlib import Path
import pytest
import onsrap.execution as execution_module

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
def execution(config, logger, stageresult) -> ExecutionContext:
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
        {"stage_test":stageresult},
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


def test_executioncontext_creation(execution, logger, config, stageresult) -> None:
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
    assert execution.stage_results == {"stage_test":stageresult}
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
    
    
    result = execution.resolve_data_root(None)
    expected = (
        Path(execution_module.__file__).resolve().parents[1]
        / "data"
    )
    assert result == expected

def test_resolve_output_root(execution) -> None: 
    """
    Tests that resolve_output_root method extracts the path from the given run 
    directory or, if None are given, returns the file path for the module itself
    and the data directory within that. 
    """
    run_dir = Path("tmp/run")
    assert execution.resolve_output_root(run_dir) == Path("tmp/run/data")

    result = execution.resolve_output_root(None)
    expected = (
        Path(execution_module.__file__).resolve().parents[1]
        / "data"
    )
    assert result == expected

"""
Parameters for testing multiple add_folder options in 
test_resolve_given_path_add_folders function.
"""
@pytest.mark.parametrize(
        "add_folder,file_name,expected",
        [
            (
                ["interim","testing_files"],
                "clean.py",
                Path("tmp/data/interim/testing_files/clean.py")
            ),
            (
                "interim",
                "clean.py",
                Path("tmp/data/interim/clean.py")
             ),
             (
                None, 
                "clean.py",
                Path("tmp/data/clean.py")
             ),
              (
                ["interim","testing_files"],
                None,
                Path("tmp/data/interim/testing_files")
            ),
            (
                "interim",
                None,
                Path("tmp/data/interim")
             ),
             (
                None, 
                None,
                Path("tmp/data")
              )
        ],
)


def test_resolve_given_path_add_folders(execution, add_folder, file_name, expected) -> None: 
    """
    Tests the add_folder functionality for lists, single strings, or None type in 
    the resolve_given_path class method as well as when the file_name is a valid string
    or None type. 
    """
    path_name = "data_path"
    root = Path("tmp/data")

    assert execution.resolve_given_path(None, 
                                         path_name, 
                                         file_name, 
                                         root, 
                                         add_folder) == expected

def test_resolve_given_path_norm(execution) -> None:  
    """
    Tests that resolve_given_path returns a file path that has been output in a
    StageResult instance.
    """  
    execution.record(StageResult("stage_test2",
                                StageStatus.PENDING,
                                '2024-05-06 15:45:30',
                                '2024-05-07 15:45:30',
                                metadata={},
                                outputs = {"data_path":"clean.py"} ))
    stage_name = "stage_test2"
    path_name = "data_path"
    root = Path("tmp/data")

    assert execution.resolve_given_path(stage_name,
                                        path_name,
                                        None,
                                        root,
                                        None) == Path("clean.py")
    
"""TEST NOT RUN FOR StageExecutor AS COVERED UNDER PythonStageExecutor"""

@pytest.fixture
def pythonstageexecutor() -> PythonStageExecutor:
    return PythonStageExecutor(("main.py","run.py"))

def test_pythonstageexecutor_setup(pythonstageexecutor) -> None: 
    assert pythonstageexecutor.preferred_entrypoints == ("main.py","run.py")

"""CONTINUE FROM EXECUTE CLASS METHOD"""