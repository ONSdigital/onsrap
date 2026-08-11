import logging
from unittest import mock
import warnings

from onsrap.loader import load_historical_run
from onsrap.pipeline import Pipeline, PipelineConfig
from onsrap.execution import PythonStageExecutor
from onsrap.errors import HistoricalPipelineLoadError, PipelineInitialisationError, PipelineConfigurationError, StageConfigurationError, StageLoadError
from onsrap.models import PipelineRun, StageConfig
from onsrap.stage import Stage
from onsrap.warnings import StageConfigurationWarning
from onsrap.logger import Logger

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

def test_generate_context_correctly_assigns_executor() -> None: 
    """
    Test that the correct executor class is assigned to the Pipeline instance
    based on the backend specified. If the backend does not have a compatible 
    executor, an error is raised. 
    """

    with pytest.warns(PipelineConfigurationWarning,
                          match = "No stages specified to run. All stages running by default."):
        pipeline = Pipeline(backend="python",
                            stages=[Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())])
    assert isinstance(pipeline.executor, PythonStageExecutor)

    with pytest.raises(PipelineInitialisationError):
        Pipeline(backend="nonexistent_backend",
                 stages=[Stage("Stage_0", source=Path("Stage_0.py"), dependencies=())])

def test_validate_stage_backends_errors() -> None: 
    """
    Test that the _validate_stage_backends method correctly raises an error if 
    the backends for a stage do not match the Pipeline backend or if there are 
    multiple backends across the stages. 

    Successful runs not tested here as they are covered in test_generate_context_
    correctly_assigns_executor(). 
    """

    with pytest.raises(PipelineInitialisationError):
        Pipeline(
            backend="python",
            stages=[
                Stage(
                    "Stage_0",
                    source=Path("Stage_0.py"),
                    dependencies=(),
                    backend="nonexistent_backend",
                )
            ],
        )

    with pytest.raises(PipelineInitialisationError):
        Pipeline(
            backend="python",
            stages=[
                Stage(
                    "Stage_0",
                    source=Path("Stage_0.py"),
                    dependencies=(),
                    backend="nonexistent_backend",
                ),
                Stage(
                    "Stage_1",
                    source=Path("Stage_1.py"),
                    dependencies=(),
                    backend="python",
                ),
            ],
        )

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
                    stage_results: {{}}
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
            ),
            stages = [Stage("Stage_0", source=tmp_path/"Stage_0.py", dependencies=())])
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

class TestExtractHistoricalRunIds(TestLoadLatestRunIntegration):
    def test_logger_no_handler_errors(self,
                                   tmp_path: Path) -> None:
        """
        Tests that if the logger has no handlers, an error is raised when 
        attempting to extract historical ids as the logger is not writing
        to a file that can be checked.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        
        Raises
        ------
        ``HistoricalPipelineLoadError``
            Raised when the logger does not have any handlers, indicating that
            it is not writing to a file path and cannot extract historical run ids.
        """
        logger = Logger(log_dir = tmp_path/"logs")
        logger._logger.handlers.clear()  # Remove all handlers to simulate no file logging
        logger._logger.propagate = False  # Prevent checking root logger handlers
        with pytest.raises(HistoricalPipelineLoadError, match="does not write to a"):
            logger.extract_historical_run_ids(run_root = tmp_path/"runs")

    def test_logger_no_file_handler_errors(self,
                                   tmp_path: Path) -> None:
        """
        Tests that if the logger has no file handlers, an error is raised when 
        attempting to extract historical ids as the logger is not writing
        to a file that can be checked.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        
        Raises
        ------
        ``HistoricalPipelineLoadError``
            Raised when the logger does not have any handlers, indicating that
            it is not writing to a file path and cannot extract historical run ids.
            """
        logger = Logger(log_dir = tmp_path/"logs")
        logger._logger.handlers = [logging.StreamHandler()]
        with pytest.raises(HistoricalPipelineLoadError, match="does not have a FileHandler"):
            logger.extract_historical_run_ids(run_root = tmp_path/"runs")

    def test_logger_does_not_exist(self,
                                   tmp_path:Path) -> None:
         """
         Checks that the method raises an error if the log doesn't exist at the
         location specified. 

         Parameters
         ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
         """
         logger = Logger(log_dir = tmp_path/"logs")

         file_handler = next(
            h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
         )

         log_path = Path(file_handler.baseFilename)

         file_handler.close()
         log_path.unlink(missing_ok=True)  # Remove the log file to simulate non-existence

         with pytest.raises(HistoricalPipelineLoadError, 
                            match="does not exist at this location"):
             logger.extract_historical_run_ids(run_root = tmp_path/"runs")

    def test_return_blank_list_no_matches_in_log(self,
                                                 tmp_path) -> None:
        """
        Tests that a log file that does not have a record covering "Pipeline started"
        will return a blank list from extract_historical_run_ids.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        logger = Logger(log_dir = tmp_path/"logs")

        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                 )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text("2026-08-10 10:00:00,000 Some unrelated log entry\n" \
        "2026-08-10 10:00:01,000 Another unrelated log entry\n")

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result == []

    def test_skips_poor_json_in_log(self,
                                    tmp_path: Path) -> None:
        """
        Tests that if a JSON record in the log file is not valid, it will e skipped
        and the next valid entry will be extracted. Assert that the returned list 
        contains only the valid entry. Confirms that only the incorrect record is 
        skipped.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        logger = Logger(log_dir = tmp_path/"logs")
        
        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                    )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text("2026-08-10 10:00:00,000 Pipeline started | not_valid_json\n" \
        "2026-08-10 10:00:01,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_878fcb33\"}\n" \
        "2026-08-10 10:00:02,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_abc1234\"}\n")

        create_run_dir_1 = tmp_path/"runs"/"2026-06-23_101719_878fcb33"
        create_run_dir_1.mkdir(parents=True, exist_ok=True)

        create_run_dir_2 = tmp_path/"runs"/"2026-06-23_101719_abc1234"
        create_run_dir_2.mkdir(parents=True, exist_ok=True)

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result == [
            {
            "run_id": "2026-06-23_101719_abc1234", 
            "timestamp": "2026-08-10 10:00:02,000", 
            "run_dir": tmp_path/"runs"/"2026-06-23_101719_abc1234"
            },
            {
            "run_id": "2026-06-23_101719_878fcb33", 
            "timestamp": "2026-08-10 10:00:01,000", 
            "run_dir": tmp_path/"runs"/"2026-06-23_101719_878fcb33"}
            ]

    @pytest.mark.parametrize("string, expected", 
                             [('{"some_key":"some_value"}', []),
                                                  ('{"run_id":""}',[])])

    def test_run_id_absent_falsy(self,
                          tmp_path: Path,
                          string: str,
                          expected: list) -> None:
        """
        Tests that if the JSON record in the log file does not have a run_id, it will be skipped
        and the returned list will be empty. 

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        ``string`` : str
            A dictionary representing a valid JSON record in the log file that excludes
            run_id.
        ``expected`` : list
            The expected output from extract_historical_run_ids when the log file 
            contains a record without a run_id.
        """
        logger = Logger(log_dir = tmp_path/"logs")
                
        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                    )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text(
        f"2026-08-10 10:00:01,000 Pipeline started | {string}\n")

        #creates directory for runs to avoid removal given the directory doesn't exist
        (tmp_path/"runs").mkdir(parents=True, exist_ok=True)

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result == expected

    def test_records_only_if_directory_exists(self,
                                              tmp_path) -> None: 
        """
        Checks that a record is only output if the run directory exists.
        
        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        
        logger = Logger(log_dir = tmp_path/"logs")
        
        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                    )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text(
        "2026-08-10 10:00:01,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_878fcb33\"}\n" \
        "2026-08-10 10:00:02,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_abc1234\"}\n")

        create_run_dir_1 = tmp_path/"runs"/"2026-06-23_101719_878fcb33"
        create_run_dir_1.mkdir(parents=True, exist_ok=True)

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result == [
            {
            "run_id": "2026-06-23_101719_878fcb33", 
            "timestamp": "2026-08-10 10:00:01,000", 
            "run_dir": tmp_path/"runs"/"2026-06-23_101719_878fcb33"}
            ]

    def test_reverse_chronological_order(self,
                                         tmp_path) -> None:
        """
        Checks that the run_ids are output in reverse chronological order
        based on their positioning in the log file.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        logger = Logger(log_dir = tmp_path/"logs")
        
        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                    )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text(
        "2026-08-10 10:00:01,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_878fcb33\"}\n" \
        "2026-08-10 10:00:02,000 Pipeline started | {\"run_id\": \"2026-06-23_101719_abc1234\"}\n")

        create_run_dir_1 = tmp_path/"runs"/"2026-06-23_101719_878fcb33"
        create_run_dir_1.mkdir(parents=True, exist_ok=True)

        create_run_dir_2 = tmp_path/"runs"/"2026-06-23_101719_abc1234"
        create_run_dir_2.mkdir(parents=True, exist_ok=True)

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result[0]["run_id"] == "2026-06-23_101719_abc1234"
        assert result[1]["run_id"] == "2026-06-23_101719_878fcb33"

    def test_skip_poor_timestamps(self,
                                   tmp_path) -> None:
        """
        Checks that entries with poor timestamps are skipped.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        """
        logger = Logger(log_dir = tmp_path/"logs")
        
        file_handler = next(
                    h for h in logger._logger.handlers if isinstance(h, logging.FileHandler)
                    )
        
        log_path = Path(file_handler.baseFilename)

        log_path.write_text(
        "BADTIMESTAMP Pipeline started | {\"run_id\": \"2026-06-23_101719_878fcb33\"}\n")

        create_run_dir_1 = tmp_path/"runs"/"2026-06-23_101719_878fcb33"
        create_run_dir_1.mkdir(parents=True, exist_ok=True)

        result = logger.extract_historical_run_ids(run_root = tmp_path/"runs")
        assert result == []

class TestLoadHistoricalRun(TestLoadLatestRunIntegration):
    def test_raises_stageloaderror_no_file(self,
                                           tmp_path: Path) -> None:
        """
        Checks that load_historical_run raises a StageLoadError when the specified
        directory does not contain any files matching the expected pattern. 

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        
        Raises
        ------
        ``StageLoadError``
            Raised when the specified directory does not contain any files matching
            the expected pattern for historical run YAML files.
        """
        run_dir = tmp_path/"empty_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(StageLoadError, match="Historical run file does not exist"):
            load_historical_run(run_dir=run_dir)

    def test_returns_valid_pipeline_run_from_yaml(self,
                                                  tmp_path:Path,
                                                  minimal_pipeline_yaml)-> None:
        """
        Checks that load_historical_run successfully returns a PipelineRun instance.
        
        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files
            and directories.
        ``minimal_pipeline_yaml`` : callable
            A fixture that returns a minimal YAML configuration for a historical run.
        """

        run_dir = tmp_path/"valid_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir/"pipeline_attributes_for_test.yaml").write_text(
            minimal_pipeline_yaml(run_id = "test_id"), encoding="utf-8")

        result = load_historical_run(run_dir=run_dir)
        assert isinstance(result, PipelineRun)
        assert result.manifest.run_id == "test_id"

    def test_correct_yaml_file_chosen(self,
                                      tmp_path: Path,
                                      minimal_pipeline_yaml) -> None:
        """
        Checks that if there are multiple files within the same run directory, 
        the method will pass successfully and return a PipelineRun. This does
        not assert which file is chosen, only that the method does not raise 
        an error and returns a PipelineRun instance.

        Logically, this should be suitable as we would only ever expect one file
        to be present in each run directory.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        ``minimal_pipeline_yaml`` : callable
            A fixture that returns a minimal YAML configuration for a historical run.
        """
        run_dir = tmp_path/"multiple_runs"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir/"pipeline_attributes_for_test1.yaml").write_text(
            minimal_pipeline_yaml(run_id = "test_id_1"), encoding="utf-8")
        (run_dir/"pipeline_attributes_for_test2.yaml").write_text(
            minimal_pipeline_yaml(run_id = "test_id_2"), encoding="utf-8")

        result = load_historical_run(run_dir=run_dir)
        assert isinstance(result, PipelineRun)

class TestLoadLatestIntegrationInPipeline(TestLoadLatestRunIntegration):
    def test_no_previous_runs_pipeline(self, tmp_path: Path) -> None:
        """
        Tests that if a Pipeline instance has no previous runs, the _load_latest_run
        method will return None and raise a warning. Assert that it will also store 
        None in the last_run attribute of the Pipeline instance.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.

        Raises
        ------
        ``PipelineConfigurationWarning``
            Raised when no previous runs are found for the Pipeline, indicating 
            that the last_run attribute will be None.
        """
        with pytest.warns(PipelineConfigurationWarning):
            pipeline = Pipeline(
                config=PipelineConfig(output_dir=tmp_path / "outputs"),
                stages=[Stage("Stage_0", source=tmp_path / "Stage_0.py", dependencies=())],
            )
        pipeline.run_output = tmp_path / "runs"
        assert pipeline.last_run is None

    def test_last_run_populated_one_run(self,
                                        tmp_path: Path,
                                        minimal_pipeline_yaml) -> None:
        """
        Tests that if a Pipeline instance has one previous run, this is loaded in 
        last_run attribute at Pipeline creation. 

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary directory provided by pytest for creating test files 
            and directories.
        ``minimal_pipeline_yaml`` : callable
            A fixture that returns a minimal YAML configuration for a historical run.

        Raises
        ------
        ``PipelineConfigurationWarning``
            Raised when there is no stages_to_run parameters to warn the user that 
            all stages will be run by default.
        """
        logs = tmp_path / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "onsrap.log").write_text(
            "2026-08-11 10:00:00,000 Pipeline started | "
            "{\"run_id\": \"2026-08-11_100000_abc12345\", "
            " \"run_dir\": \"/path/to/run\"}\n"
        )

        temp_attributes = (tmp_path / "outputs" / "runs" / "2026-08-11_100000_abc12345"
                            / "pipeline_attributes_for_test.yaml")
        temp_attributes.parent.mkdir(parents=True, exist_ok=True)
        temp_attributes.write_text(minimal_pipeline_yaml(
            run_id = "2026-08-11_100000_abc12345"
            ), encoding="utf-8")

        with pytest.warns(PipelineConfigurationWarning):
            pipeline = Pipeline(
                config=PipelineConfig(output_dir=tmp_path / "outputs",
                                        log_dir=logs),
                stages=[Stage("Stage_0", source=tmp_path / "Stage_0.py", dependencies=())],
            )

        assert pipeline.last_run is not None
        assert pipeline.last_run.manifest.run_id == "2026-08-11_100000_abc12345"