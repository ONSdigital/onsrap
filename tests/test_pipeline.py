from unittest import mock
import warnings

from onsrap.pipeline import Pipeline, PipelineConfig
from onsrap.errors import PipelineInitialisationError, PipelineConfigurationError, StageConfigurationError
from onsrap.models import PipelineRun, PipelineRun, StageConfig
from onsrap.stage import Stage
from onsrap.warnings import StageConfigurationWarning
from pathlib import Path
import pytest

from onsrap.warnings import PipelineConfigurationWarning

def test_pipeline_name():
    """
    Test to confirm that Pipeline instance uses either defined name from 
    instance creation (shown in pipeline_named), utilises name from PipelineConfig
    if no name was given (shown in pipeline_config), or defaults to "pipeline" if
    no name is provided through Pipeline instance creation or through the 
    PipelineConfig (shown through pipeline_no_name)
    """
    pipeline_config = PipelineConfig(name = "test_pipeline_config")

    with pytest.warns(PipelineConfigurationWarning,
                      match = "No stages specified to run. All stages running by default."):
        pipeline_named = Pipeline(name = "test_pipeline_name")
        pipeline_config = Pipeline(name = None, config = pipeline_config)
        pipeline_no_name = Pipeline()

    assert pipeline_named.name == "test_pipeline_name"
    assert pipeline_config.name == "test_pipeline_config"
    assert pipeline_no_name.name == "pipeline"


def test_assign_dependencies(tmp_path):
    """
    Test to ensure that different formats of dependencies can be parsed to the 
    Pipeline creation and appropriately assigned to each stage within the 
    Pipeline. Will also check for error raise if the dependencies are defined 
    but there are no defined stages. 
    """
    def example_function():
        pass

    path_1 = tmp_path/"Stage_1.py"
    path_0 = tmp_path/"Stage_0.py"

    dependencies_single = {"Stage_2":("Stage_1",)}
    dependencies_multiple = {"Stage_1":["Stage_0"],
                             "Stage_2":("Stage_1", "Stage_0")}
    dependencies_non_stage_name = {"Stage_1.py":("Stage_0",),
                                   "example_function":("Stage_1.py",)}
    
    with pytest.raises(PipelineInitialisationError):
        Pipeline(stages = None,
                 dependencies = dependencies_single)

    with pytest.warns(PipelineConfigurationWarning,
                      match = "No stages specified to run. All stages running by default."):
        pipeline_1 = Pipeline(name = "pipeline_1",
                            stages = [Stage("Stage_1", path_1, None,{}), 
                                        Stage("Stage_2", example_function, None,{}),
                                        Stage("Stage_0", path_0, None,{}),],
                            dependencies = dependencies_multiple)
        
        pipeline_2 = Pipeline(name = "pipeline_2",
                                stages = [Stage("Stage_1.py", path_1, None,{}), 
                                            Stage("Stage_2", example_function, None,{}),
                                            Stage("Stage_0", path_0, None,{}),],
                                dependencies = dependencies_non_stage_name)
            
    assert pipeline_1.stages[0].dependencies == ("Stage_0",)
    assert pipeline_1.stages[1].dependencies == ("Stage_1","Stage_0")

    assert pipeline_2.stages[0].dependencies == ("Stage_0",)
    assert pipeline_2.stages[1].dependencies == ("Stage_1.py",)
    
    
def test_add_dependencies_single_dict(tmp_path): 
    """
    Tests that a dictionary correctly assigns dependencies to 
    individual stages and the Pipeline instance. 
    """
    
    path_1 = tmp_path/"Stage_1.py"
    path_2 = tmp_path/"Stage_2.py"
    path_0 = tmp_path/"Stage_0.py"

    dependencies_multiple = {"Stage_0":(),
                             "Stage_1":(),
                             "Stage_2":("Stage_1",)}
    dep_dict = {"Stage_1":("Stage_0",),
                "Stage_2":("Stage_0","Stage_1")}
    dep_tuple = ("Stage_0.25",)
    stage_1 = Stage("Stage_1", source = path_1, dependencies = {})
    stage_2 = Stage("Stage_2", source = path_2, dependencies = {})
    stage_0 = Stage("Stage_0", source = path_0, dependencies = {})

    with pytest.warns(PipelineConfigurationWarning,
                      match = "No stages specified to run. All stages running by default."):   
        pipeline_dict = Pipeline(stages = [stage_0, stage_1, stage_2],
                                        dependencies = dependencies_multiple)
    
    with pytest.raises(PipelineInitialisationError):
        pipeline_dict.add_dependencies(dep_tuple)

    pipeline_dict.add_dependencies(dep_dict)
    assert stage_1.dependencies == ("Stage_0",)
    assert stage_2.dependencies == ("Stage_1","Stage_0",)
    assert stage_0.dependencies == ()
    assert pipeline_dict.dependencies == {"Stage_0":(),
                             "Stage_1":("Stage_0",),
                             "Stage_2":("Stage_1","Stage_0",)}


def test_add_stage_parses_stage_configs_keyword() -> None:
    pipeline = Pipeline()
    stage = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=())
    stage_config = StageConfig(name="Stage_1", _variables={"years_to_run": 2017})

    pipeline.add_stage(stage, stage_configs=[stage_config])

    assert pipeline.stages[-1].name == "Stage_1"
    assert pipeline.stage_configs["Stage_1"].require("years_to_run") == 2017


def test_add_stage_warns_when_stage_config_count_mismatches() -> None:
    pipeline = Pipeline()
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=())

    with pytest.warns(StageConfigurationWarning) as recorded_warnings:
        pipeline.add_stage(stage_0, stage_1, stage_configs=[{"years_to_run": 2017}])

    assert any(
        "does not match the number of stages" in str(recorded_warning.message)
        for recorded_warning in recorded_warnings
    )
    assert pipeline.stage_configs["Stage_0"].require("years_to_run") == 2017
    assert pipeline.stage_configs["Stage_1"].to_dict() == {}


def test_add_stage_config_coerces_mapping_payload_for_named_stage() -> None:
    pipeline = Pipeline(stages=[Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())])

    pipeline.add_stage_config({"years_to_run": 2017}, name="Stage_0")

    assert pipeline.stage_configs["Stage_0"].require("years_to_run") == 2017


# ---------------------------------------------------------------------------
# Stage graph and stage-selection tests
# ---------------------------------------------------------------------------

def test_resolve_stages_to_run_includes_transitive_dependencies() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=("Stage_0",))
    stage_2 = Stage("Stage_2", source=Path("Stage_2.py"), dependencies=("Stage_1",))

    pipeline = Pipeline(
        stages=[stage_0, stage_1, stage_2],
        config=PipelineConfig(stages_to_run={"Stage_2": True}),
    )

    assert [stage.name for stage in pipeline.graph.stages] == ["Stage_0", "Stage_1", "Stage_2"]
    assert [stage.name for stage in pipeline.ordered_stages()] == ["Stage_0", "Stage_1", "Stage_2"]


def test_resolve_stages_to_run_rejects_disabled_dependencies() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=("Stage_0",))

    with pytest.raises(PipelineConfigurationError):
        Pipeline(
            stages=[stage_0, stage_1],
            config=PipelineConfig(stages_to_run={"Stage_0": False, "Stage_1": True}),
        )


def test_self_stages_is_full_registry_after_disable() -> None:
    """Pipeline.stages always holds all stages; only graph.stages is the effective run set."""
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=())
    pipeline = Pipeline(stages=[stage_0, stage_1])

    pipeline.disable_stage("Stage_1")

    assert [stage.name for stage in pipeline.stages] == ["Stage_0", "Stage_1"]
    assert [stage.name for stage in pipeline.graph.stages] == ["Stage_0"]
    assert [stage.name for stage in pipeline.ordered_stages()] == ["Stage_0"]


def test_disable_stage_in_implicit_mode_creates_explicit_selection() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=())
    pipeline = Pipeline(stages=[stage_0, stage_1])

    pipeline.disable_stage("Stage_1")

    assert pipeline.config.stages_to_run == {"Stage_0": True, "Stage_1": False}


def test_enable_stage_restores_stage_in_explicit_mode() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=())
    pipeline = Pipeline(
        stages=[stage_0, stage_1],
        config=PipelineConfig(stages_to_run={"Stage_0": True, "Stage_1": False}),
    )

    pipeline.enable_stage("Stage_1")

    assert pipeline.config.stages_to_run["Stage_1"] is True
    assert {stage.name for stage in pipeline.graph.stages} == {"Stage_0", "Stage_1"}


def test_add_stage_keeps_new_stage_out_of_explicit_selection() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    pipeline = Pipeline(
        stages=[stage_0],
        config=PipelineConfig(stages_to_run={"Stage_0": True}),
    )

    pipeline.add_stage(
        Stage("Stage_1", source=Path("Stage_1.py"), dependencies=()),
        stage_configs=[StageConfig(name="Stage_1")],
    )

    assert pipeline.config.stages_to_run["Stage_1"] is False
    assert [stage.name for stage in pipeline.graph.stages] == ["Stage_0"]

def test_add_stage_adds_new_stage_to_explicit_selection_when_enable_stages_is_true() -> None:
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    pipeline = Pipeline(
        stages=[stage_0],
        config=PipelineConfig(stages_to_run={"Stage_0": True}),
    )

    pipeline.add_stage(
        Stage("Stage_1", source=Path("Stage_1.py"), dependencies=()),
        stage_configs=[StageConfig(name="Stage_1")],
        enable_stages=True,
    )

    assert pipeline.config.stages_to_run["Stage_1"] is True
    assert {stage.name for stage in pipeline.graph.stages} == {"Stage_0", "Stage_1"}


def test_validate_skips_source_check_for_disabled_stages(tmp_path: Path) -> None:
    """Disabled stages' source files need not exist — validate() only checks the effective run set."""
    enabled_file = tmp_path / "Stage_0.py"
    enabled_file.write_text("def run(ctx): pass\n", encoding="utf-8")

    stage_0 = Stage("Stage_0", source=enabled_file)
    stage_1 = Stage("Stage_1", source=tmp_path / "missing.py")  # file intentionally absent

    pipeline = Pipeline(
        stages=[stage_0, stage_1],
        config=PipelineConfig(stages_to_run={"Stage_0": True, "Stage_1": False}),
    )

    pipeline.validate()  # must not raise


def test_construct_manifest_inputs_contains_only_effective_stages() -> None:
    """Manifest inputs should list only the stages that are part of the execution graph."""
    stage_0 = Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())
    stage_1 = Stage("Stage_1", source=Path("Stage_1.py"), dependencies=("Stage_0",))
    pipeline = Pipeline(
        stages=[stage_0, stage_1],
        config=PipelineConfig(stages_to_run={"Stage_0": True, "Stage_1": False}),
    )

    runtime_id = pipeline._create_runtime_id()
    manifest = pipeline._construct_manifest(runtime_id=runtime_id)

    assert list(manifest.inputs.keys()) == ["Stage_0"]


class TestLoadLatestRunIntegration:
    @pytest.fixture
    def pipeline_log_line(self):
        def _make(run_id: str, timestamp: str) -> str:
            """
            Returns a false log file line to simulate a historical run in the log file.
            The line is formatted to match the expected log output.

            Parameters
            ----------
            ``run_id`` : str
                The unique identifier for the historical run.
            ``timestamp`` : str
                The timestamp of when the historical run was initiated.
            """
            return f"{timestamp} Pipeline started | " \
                f"{{\"run_id\": \"{run_id}\", \"run_dir\": \"/path/to/run\"}}"
        return _make

    @pytest.fixture
    def minimal_pipeline_yaml(self):
        def _make(run_id: str) -> str:
            """
            Returns a minimal YAML configuration for a historical run.

            Parameters
            ----------
            ``run_id`` : str
                The unique identifier for the historical run.
            """
            return f"""
                    manifest:
                        run_id: {run_id}
                    status: succeeded
                    started_at: '2026-08-06T17:03:30.000077'
                    completed_at: '2026-08-06T17:03:30.031654'
                    stage_results: []
                    stage_outputs: {{}}
                    """
        return _make

class TestLoadLatestRun(TestLoadLatestRunIntegration):
    @pytest.fixture
    def pipeline_no_history(self, tmp_path: Path) -> Pipeline:
        """
        Sets up a blank pipeline instance for testing that accounts for warnings
        in init phase rather than dealing with these in the tests.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        with pytest.warns(PipelineConfigurationWarning):
            pipeline = Pipeline(config=PipelineConfig(
                output_dir = tmp_path/"outputs",
            ))
        pipeline.run_output = tmp_path/"runs"
        return pipeline
    
    def test_blank_historical_run_ids(self, 
                                      pipeline_no_history: Pipeline, 
                                      monkeypatch) -> None:
        """
        Tests that if extract_historical_run_ids returns a blank list, the
        _load_latest_run method will return None and raise a warning. Assert
        that it will also store None in the last_run attribute of the Pipeline
        instance. 

        Parameters
        ----------
        ``pipeline_no_history`` : Pipeline
            A Pipeline instance with no historical runs.
        ``monkeypatch`` : pytest.MonkeyPatch
            A pytest fixture that allows for dynamic modification of attributes, 
            methods, or classes during testing.

        Raises
        ------
        ``PipelineConfigurationWarning``
            Raised when no previous runs are found for the Pipeline, indicating 
            that the last_run attribute will be None.
        """
        monkeypatch.setattr(pipeline_no_history.logger, 
                            "extract_historical_run_ids", 
                            lambda x: [])
        assert pipeline_no_history.logger.extract_historical_run_ids(
            pipeline_no_history.run_output
            ) == []
        with pytest.warns(PipelineConfigurationWarning, match="No previous runs " \
        "found for this Pipeline. Last_run attribute will be None."):
            assert pipeline_no_history._load_latest_run() == None
            assert pipeline_no_history.last_run == None

    def test_blank_run_ids(self,
                           pipeline_no_history: Pipeline,
                           monkeypatch) -> None:
        """
        Tests that if the found log record does not have a run_id, _load_latest_run
        will return None and raise a warning. Assert that it will also store None
        in the last_run attribute of the Pipeline instance.

        Parameters
        ----------
        ``pipeline_no_history`` : Pipeline
            A Pipeline instance with no historical runs.
        ``monkeypatch`` : pytest.MonkeyPatch
            A pytest fixture that allows for dynamic modification of attributes, 
            methods, or classes during testing.

        Raises
        ------
        ``PipelineConfigurationWarning``
            Raised when no previous runs are found for the Pipeline, indicating 
            that the last_run attribute will be None.
        """
        monkeypatch.setattr(pipeline_no_history.logger, 
                            "extract_historical_run_ids", 
                            lambda x: [{
                                "run_id": None, 
                                "timestamp": "2026-08-10 10:00:00,000", 
                                "run_dir": Path("/")}]
                                )
        assert pipeline_no_history.logger.extract_historical_run_ids(
            pipeline_no_history.run_output
            ) == [{
                "run_id": None, 
                "timestamp": "2026-08-10 10:00:00,000", 
                "run_dir": Path("/")
                }]
        with pytest.warns(PipelineConfigurationWarning, match="No previous runs " \
        "found for this Pipeline. Last_run attribute will be None."):
                    assert pipeline_no_history._load_latest_run() == None
                    assert pipeline_no_history.last_run == None
        
    def test_load_latest_run_success(self,
                                     monkeypatch,
                                     pipeline_no_history: Pipeline) -> None:

        """
        Tests that load_latest_run works successfully with fully mocked data. 

        Parameters
        ----------
        ``monkeypatch`` : pytest.MonkeyPatch
            A pytest fixture that allows for dynamic modification of attributes, 
            methods, or classes during testing.
        ``pipeline_no_history`` : Pipeline
            A Pipeline instance with no historical runs.
        """

        expected_run = mock.MagicMock(spec=PipelineRun)
        run_id = "2026-08-10_100000_abc12345"
        monkeypatch.setattr(
            pipeline_no_history.logger,
            "extract_historical_run_ids", 
            lambda _: [{
                "run_id": run_id,
                "timestamp": "2026-08-10 10:00:00,000",
                "run_dir": Path("/path/to/run")
            }]
        )

        mock_load_historical_run = mock.MagicMock(return_value=expected_run)
        monkeypatch.setattr("onsrap.pipeline.load_historical_run", 
                            mock_load_historical_run)

        result = pipeline_no_history._load_latest_run()

        assert result is expected_run

        expected_path = pipeline_no_history.run_output / run_id
        mock_load_historical_run.assert_called_once_with(run_dir = expected_path)

    def test_which_run_is_selected_load_latest_run(self,
                                                   monkeypatch,
                                                   pipeline_no_history: Pipeline
                                                   ) -> None:

        """
        Checks that the first item is selected from the list of historical runs 
        returned by extract_historical_run_ids.

        Parameters
        ----------
        ``monkeypatch`` : pytest.MonkeyPatch
            A pytest fixture that allows for dynamic modification of attributes, 
            methods, or classes during testing.
        ``pipeline_no_history`` : Pipeline
            A Pipeline instance with no historical runs.
        """
        expected_run = mock.MagicMock(spec=PipelineRun)
        run_id_1 = "2026-08-10_100000_abc12345"
        run_id_2 = "2026-08-10_100000_def67890"
        monkeypatch.setattr(
            pipeline_no_history.logger,
            "extract_historical_run_ids", 
            lambda _: [
                {
                "run_id": run_id_1,
                "timestamp": "2026-08-10 10:00:00,000",
                "run_dir": "run_A"
            },
            {
            "run_id": run_id_2,
            "timestamp": "2026-08-10 10:00:00,000",
            "run_dir": "run_B"
            }
            ]
        )

        mock_load_historical_run = mock.MagicMock(return_value=expected_run)
        monkeypatch.setattr("onsrap.pipeline.load_historical_run", 
                            mock_load_historical_run)

        pipeline_no_history._load_latest_run()

        expected_path = pipeline_no_history.run_output / run_id_1
        mock_load_historical_run.assert_called_once_with(run_dir = expected_path)

        #does not refer to run_dir in the extract_historical_run_ids list but the 
        #parameter required in load_historical_run.
        assert mock_load_historical_run.call_args.kwargs["run_dir"].name == run_id_1

    def test_no_errors_raised_success_load_latest_run(self,
                                         monkeypatch,
                                         pipeline_no_history: Pipeline) -> None:
    
        """
        Tests that no errors are raised when load_latest_run is successful. 

        Parameters
        ----------
        ``monkeypatch`` : pytest.MonkeyPatch
            A pytest fixture that allows for dynamic modification of attributes, 
            methods, or classes during testing.
        ``pipeline_no_history`` : Pipeline
            A Pipeline instance with no historical runs.
        """

        expected_run = mock.MagicMock(spec=PipelineRun)
        run_id = "2026-08-10_100000_abc12345"
        monkeypatch.setattr(
            pipeline_no_history.logger,
            "extract_historical_run_ids", 
            lambda _: [{
                "run_id": run_id,
                "timestamp": "2026-08-10 10:00:00,000",
                "run_dir": Path("/path/to/run")
            }]
        )

        mock_load_historical_run = mock.MagicMock(return_value=expected_run)
        monkeypatch.setattr("onsrap.pipeline.load_historical_run", 
                            mock_load_historical_run)

        with warnings.catch_warnings(record=True) as w:
            pipeline_no_history._load_latest_run()

        assert not any(issubclass(warning.category, PipelineConfigurationWarning) 
                       for warning in w)

        
    
        
