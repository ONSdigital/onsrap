import datetime
from pathlib import Path
from textwrap import dedent

import pytest

from onsrap.models import (
    PipelineConfig,
    PipelineRun,
    PipelineStatus,
    RunManifest,
    RuntimeID,
    StageStatus,
)

STARTED_AT = datetime.datetime(2024, 5, 6, 15, 45, 30)
FINISHED_AT = datetime.datetime(2024, 5, 7, 15, 45, 30)


class TestStatuses:
    def test_stagestatus(self) -> None:
        """
        Test that stagestatus outputs the correct values.
        """
        assert StageStatus.PENDING == "pending"
        assert StageStatus.RUNNING == "running"
        assert StageStatus.SUCCEEDED == "succeeded"
        assert StageStatus.FAILED == "failed"
        assert StageStatus.SKIPPED == "skipped"

    def test_pipeline_status(self) -> None:
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
    return RuntimeID(
        id="abc123",
        timestamp=datetime.datetime(2026, 7, 7, 13, 5, 46),
        hash="fnruw9574893ghkwq234h5kg",
        short_hash="4h5kg",
    )


class TestRuntimeID:
    def test_runtimeID_creation(self, runtimeID) -> None:
        """
        Test that a RuntimeID is correctly created.
        """
        assert runtimeID.id == "abc123"
        assert runtimeID.timestamp == datetime.datetime(2026, 7, 7, 13, 5, 46)
        assert runtimeID.hash == "fnruw9574893ghkwq234h5kg"
        assert runtimeID.short_hash == "4h5kg"

    def test_getter_functions_runtimeID(self, runtimeID) -> None:
        """
        Tests all the getter functions for the RuntimeID instance.
        """
        assert runtimeID.get_id() == "abc123"
        assert runtimeID.get_timestamp() == datetime.datetime(2026, 7, 7, 13, 5, 46)
        assert runtimeID.get_hash() == "fnruw9574893ghkwq234h5kg"
        assert runtimeID.get_short_hash() == "4h5kg"


@pytest.fixture
def blankpipelineconfig() -> PipelineConfig:
    """
    Blank PipelineConfig instance for class method testing.
    """
    return PipelineConfig()


@pytest.fixture
def expected_pipeline_config() -> PipelineConfig:
    """
    Example PipelineConfig completed class instance for method testing.
    """
    return PipelineConfig(
        name="test_rap",
        backend="python",
        work_dir=Path("tmp/work"),
        project_root=Path("project"),
        log_dir=Path("tmp/logs"),
        data_dir=Path("tmp/data"),
        allow_subprocess_fallback=True,
        python_executable=None,
        metadata={"variables": ["name", "age"], "num_stages": 6},
    )


@pytest.fixture
def pipelineconfig(expected_pipeline_config) -> PipelineConfig:
    return expected_pipeline_config


@pytest.fixture
def mapping() -> dict:
    """
    Example mapping dictionary for use in testing from_mapping() method.
    """
    return {
        "name": "test_rap",
        "backend": "python",
        "work_dir": Path("tmp/work"),
        "project_root": Path("project"),
        "log_dir": Path("tmp/logs"),
        "data_dir": Path("tmp/data"),
        "allow_subprocess_fallback": True,
        "python_executable": None,
        "metadata": {"variables": ["name", "age"], "num_stages": 6},
    }


class TestPipelineConfig:
    def test_from_any(
        self, mapping, pipelineconfig, blankpipelineconfig, expected_pipeline_config
    ) -> None:
        """
        Test derivation for a PipelineConfig instance using the from_any() method. This
        test checks all methods EXCEPT from_file as this will be covered in another 
        test due to creation of a mock file being required.
        """
        assert blankpipelineconfig.from_any(None) == PipelineConfig()
        assert blankpipelineconfig.from_any(pipelineconfig) == expected_pipeline_config
        assert blankpipelineconfig.from_any(mapping) == expected_pipeline_config

        with pytest.raises(TypeError):
            blankpipelineconfig.from_any(11)

    def test_from_file(self, tmp_path, expected_pipeline_config) -> PipelineConfig:
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
        assert configuration == expected_pipeline_config

        fake_file = "path_not_real"
        with pytest.raises(FileNotFoundError):
            PipelineConfig.from_file(fake_file)
        with pytest.raises(TypeError):
            PipelineConfig.from_file(no_map_pipeline_config)

    def test_to_dict(self, pipelineconfig) -> None:
        """
        Test of to_dict() class method for PipelineConfig that it outputs the 
        PipelineConfig values as a dictionary.
        """

        assert pipelineconfig.to_dict() == {
            "name": "test_rap",
            "backend": "python",
            "work_dir": "tmp\\work",
            "project_root": "project",
            "output_dir": None,
            "log_dir": "tmp\\logs",
            "data_dir": "tmp\\data",
            "allow_subprocess_fallback": True,
            "python_executable": None,
            "variables": ["name", "age"],
            "num_stages": 6,
        }


@pytest.fixture
def runmanifest() -> RunManifest:
    """
    Example RunManifest class instance for testing of class method.
    """
    return RunManifest(
        "pipeline",
        "1",
        None,
        ["stage1", "stage2"],
        {"uniqueID": "example"},
        {"input_path": "input/data/example.csv"},
        {"output_path": "output/data/example.csv"},
        "python",
        ["1.3.2"],
        "",
        None,
        None,
    )


class TestStageResult:
    def test_stage_result(self, stageresult) -> None:
        """
        Uses a StageResult instance created in test_execution to ensure that
        the class instance is created suitably with required defaults.
        """
        assert stageresult.name == "stage_test"
        assert stageresult.status == "pending"
        assert stageresult.started_at == "2024-05-06 15:45:30"
        assert stageresult.finished_at == "2024-05-07 15:45:30"
        assert stageresult.outputs == "example output"
        assert stageresult.stdout == ""
        assert stageresult.stderr == ""
        assert stageresult.return_code is None
        assert stageresult.metadata == {}
        assert stageresult.error is None
        assert stageresult.source is None

    @pytest.mark.parametrize(
        "status_stage,expected_stage",
        [
            (StageStatus.PENDING, False),
            (StageStatus.RUNNING, False),
            (StageStatus.FAILED, False),
            (StageStatus.SUCCEEDED, True),
            (StageStatus.SKIPPED, False),
        ],
    )
    def test_succeeded(self, stageresult, status_stage, expected_stage) -> None:
        """
        Tests succeeded() method for StageResult which outputs True or False depending
        on the status of the StageResult.
        """
        stageresult.status = status_stage
        assert stageresult.succeeded == expected_stage

    def test_duration_seconds(self, stageresult) -> None:
        stageresult.started_at = STARTED_AT
        stageresult.finished_at = FINISHED_AT
        seconds_value = (FINISHED_AT - STARTED_AT).total_seconds()
        assert stageresult.duration_seconds == seconds_value


@pytest.fixture
def pipelinerun(stageresult, runmanifest) -> PipelineRun:
    return PipelineRun(
        runmanifest,
        PipelineStatus.SUCCEEDED,
        STARTED_AT,
        FINISHED_AT,
        [stageresult],
        {"stage_test": "example output"},
    )


class TestPipelineRun:
    def test_pipelinerun_configuration(
        self, pipelinerun, runmanifest, stageresult
    ) -> None:
        assert pipelinerun.manifest == runmanifest
        assert pipelinerun.status == PipelineStatus.SUCCEEDED
        assert pipelinerun.started_at == STARTED_AT
        assert pipelinerun.completed_at == FINISHED_AT
        assert pipelinerun.stage_results == [stageresult]
        assert pipelinerun.stage_outputs == {"stage_test": "example output"}

    def test_result_for(self, pipelinerun, stageresult) -> None:
        assert pipelinerun.result_for("stage_test") == stageresult
        assert pipelinerun.result_for("not_a_stage") is None

    @pytest.mark.parametrize(
        "status,expected",
        [
            (PipelineStatus.PENDING, False),
            (PipelineStatus.RUNNING, False),
            (PipelineStatus.FAILED, False),
            (PipelineStatus.SUCCEEDED, True),
        ],
    )
    def test_succeeded_pipeline(self, pipelinerun, status, expected) -> None:
        pipelinerun.status = status
        assert pipelinerun.succeeded == expected


# TODO: Test _extract_stages_run and all methods in StageConfig class
