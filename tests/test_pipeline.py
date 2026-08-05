from pathlib import Path

import pytest

from onsrap.errors import PipelineConfigurationError, PipelineInitialisationError
from onsrap.models import StageConfig
from onsrap.pipeline import Pipeline, PipelineConfig
from onsrap.stage import Stage
from onsrap.warnings import PipelineConfigurationWarning, StageConfigurationWarning
from onsrap.execution import PythonStageExecutor

NO_STAGES_WARNING = "No stages specified to run. All stages running by default."


@pytest.fixture
def stage_factory():
    def _build_stage(name: str, dependencies=(), source: Path | None = None) -> Stage:
        """
            Function that builds a Stage object with a given name, dependencies, and a
            source file path that's built out of the name if it is not provided. This 
            standardises the creation of Stage objects for testing. 
            """
        resolved_source = source if source is not None else Path(f"{name}.py")
        return Stage(name, source=resolved_source, dependencies=dependencies)

    return _build_stage


class TestPipelineNamingAndInit:
    def test_pipeline_name(self):
        """
        Test to confirm that Pipeline instance uses either defined name from
        instance creation (shown in pipeline_named), utilises name from PipelineConfig
        if no name was given (shown in pipeline_config), or defaults to "pipeline" if
        no name is provided through Pipeline instance creation or through the
        PipelineConfig (shown through pipeline_no_name)
        """
        pipeline_config = PipelineConfig(name="test_pipeline_config")

        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline_named = Pipeline(name="test_pipeline_name")
            pipeline_config = Pipeline(name=None, config=pipeline_config)
            pipeline_no_name = Pipeline()

        assert pipeline_named.name == "test_pipeline_name"
        assert pipeline_config.name == "test_pipeline_config"
        assert pipeline_no_name.name == "pipeline"

    def test_assign_dependencies(self, tmp_path):
        """
        Test to ensure that different formats of dependencies can be parsed to the
        Pipeline creation and appropriately assigned to each stage within the
        Pipeline. Will also check for error raise if the dependencies are defined
        but there are no defined stages.
        """

        def example_function():
            pass

        path_1 = tmp_path / "Stage_1.py"
        path_0 = tmp_path / "Stage_0.py"

        dependencies_single = {"Stage_2": ("Stage_1",)}
        dependencies_multiple = {
            "Stage_1": ["Stage_0"],
            "Stage_2": ("Stage_1", "Stage_0"),
        }
        dependencies_non_stage_name = {
            "Stage_1.py": ("Stage_0",),
            "example_function": ("Stage_1.py",),
        }

        with pytest.raises(PipelineInitialisationError):
            Pipeline(stages=None, dependencies=dependencies_single)

        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline_1 = Pipeline(
                name="pipeline_1",
                stages=[
                    Stage("Stage_1", path_1, None, {}),
                    Stage("Stage_2", example_function, None, {}),
                    Stage("Stage_0", path_0, None, {}),
                ],
                dependencies=dependencies_multiple,
            )

            pipeline_2 = Pipeline(
                name="pipeline_2",
                stages=[
                    Stage("Stage_1.py", path_1, None, {}),
                    Stage("Stage_2", example_function, None, {}),
                    Stage("Stage_0", path_0, None, {}),
                ],
                dependencies=dependencies_non_stage_name,
            )

        assert pipeline_1.stages[0].dependencies == ("Stage_0",)
        assert pipeline_1.stages[1].dependencies == ("Stage_1", "Stage_0")

        assert pipeline_2.stages[0].dependencies == ("Stage_0",)
        assert pipeline_2.stages[1].dependencies == ("Stage_1.py",)

    def test_add_dependencies_single_dict(self, tmp_path):
        """
        Tests that a dictionary correctly assigns dependencies to
        individual stages and the Pipeline instance.
        """

        path_1 = tmp_path / "Stage_1.py"
        path_2 = tmp_path / "Stage_2.py"
        path_0 = tmp_path / "Stage_0.py"

        dependencies_multiple = {"Stage_0": (), "Stage_1": (), "Stage_2": ("Stage_1",)}
        dep_dict = {"Stage_1": ("Stage_0",), "Stage_2": ("Stage_0", "Stage_1")}
        dep_tuple = ("Stage_0.25",)
        stage_1 = Stage("Stage_1", source=path_1, dependencies={})
        stage_2 = Stage("Stage_2", source=path_2, dependencies={})
        stage_0 = Stage("Stage_0", source=path_0, dependencies={})

        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline_dict = Pipeline(
                stages=[stage_0, stage_1, stage_2], dependencies=dependencies_multiple
            )

        with pytest.raises(PipelineInitialisationError):
            pipeline_dict.add_dependencies(dep_tuple)

        pipeline_dict.add_dependencies(dep_dict)
        assert stage_1.dependencies == ("Stage_0",)
        assert stage_2.dependencies == (
            "Stage_1",
            "Stage_0",
        )
        assert stage_0.dependencies == ()
        assert pipeline_dict.dependencies == {
            "Stage_0": (),
            "Stage_1": ("Stage_0",),
            "Stage_2": (
                "Stage_1",
                "Stage_0",
            ),
        }


class TestPipelineStageConfigHandling:
    def test_add_stage_parses_stage_configs_keyword(self, stage_factory) -> None:
        """
        Tests that when a stage is added after a Pipeline has been initialised, 
        the stage and the stage_configurations are correctly added to the 
        Pipeline instance and the stage_configurations are correctly associated
        with the stage. 
        """
        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline = Pipeline()
            stage = stage_factory("Stage_1")
            stage_config = StageConfig(
                name="Stage_1", _variables={"years_to_run": 2017}
            )

            pipeline.add_stage(stage, stage_configs=[stage_config])

            assert pipeline.stages[-1].name == "Stage_1"
            assert pipeline.stage_configs["Stage_1"].require("years_to_run") == 2017

    def test_add_stage_warns_when_stage_config_count_mismatches(
        self, stage_factory
    ) -> None:
        """
        Tests that when a stage is added but there is not the correct number of 
        stage_configs provided, a warning is raised and the stage_configuration
        for that stage is added as a blank StageConfig object.
        """
        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline = Pipeline()
            stage_0 = stage_factory("Stage_0")
            stage_1 = stage_factory("Stage_1")

            with pytest.warns(StageConfigurationWarning) as recorded_warnings:
                pipeline.add_stage(
                    stage_0, stage_1, stage_configs=[{"years_to_run": 2017}]
                )

            assert any(
                "does not match the number of stages" in str(recorded_warning.message)
                for recorded_warning in recorded_warnings
            )
            assert pipeline.stage_configs["Stage_0"].require("years_to_run") == 2017
            assert pipeline.stage_configs["Stage_1"].to_dict() == {}

    def test_add_stage_config_coerces_mapping_payload_for_named_stage(
        self, stage_factory
    ) -> None:
        """
        Tests that when a stage_configuration is added to a Pipeline instance, 
        the configuration is correctly associated with the named stage and that
        the configuration is coerced into a StageConfig object if it is provided.
        """
        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline = Pipeline(stages=[stage_factory("Stage_0")])

        pipeline.add_stage_config({"years_to_run": 2017}, name="Stage_0")

        assert pipeline.stage_configs["Stage_0"].require("years_to_run") == 2017


class TestPipelineStageSelectionAndGraph:
    def test_resolve_stages_to_run_includes_transitive_dependencies(
        self, stage_factory
    ) -> None:
        """
        Tests that when resolving stages_to_run, the Pipeline instance correctly
        includes all dependent stages required in the StageGraph even if these
        are not explicitly called out in the configuration.
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1", dependencies=("Stage_0",))
        stage_2 = stage_factory("Stage_2", dependencies=("Stage_1",))

        pipeline = Pipeline(
            stages=[stage_0, stage_1, stage_2],
            config=PipelineConfig(stages_to_run={"Stage_2": True}),
        )

        assert [stage.name for stage in pipeline.graph.stages] == [
            "Stage_0",
            "Stage_1",
            "Stage_2",
        ]
        assert [stage.name for stage in pipeline.ordered_stages()] == [
            "Stage_0",
            "Stage_1",
            "Stage_2",
        ]

    def test_resolve_stages_to_run_rejects_disabled_dependencies(
        self, stage_factory
    ) -> None:
        """
        Checks that when resolving stages_to_run, the Pipeline init raises an
        error if a stage is enabled but one of its dependencies is disabled.
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1", dependencies=("Stage_0",))

        with pytest.raises(PipelineConfigurationError):
            Pipeline(
                stages=[stage_0, stage_1],
                config=PipelineConfig(
                    stages_to_run={"Stage_0": False, "Stage_1": True}
                ),
            )

    def test_self_stages_is_full_registry_after_disable(self, stage_factory) -> None:
        """
        Pipeline.stages always holds all stages; only graph.stages is the effective run
        set.
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1")

        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline = Pipeline(stages=[stage_0, stage_1])

        pipeline.disable_stage("Stage_1")

        assert [stage.name for stage in pipeline.stages] == ["Stage_0", "Stage_1"]
        assert [stage.name for stage in pipeline.graph.stages] == ["Stage_0"]
        assert [stage.name for stage in pipeline.ordered_stages()] == ["Stage_0"]

    def test_disable_stage_in_implicit_mode_creates_explicit_selection(
        self, stage_factory
    ) -> None:
        """
        Tests that when a stage is manually disabled in a Pipeline instance, it
        is initialised in the stages_to_run configuration. 
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1")
        with pytest.warns(PipelineConfigurationWarning, match=NO_STAGES_WARNING):
            pipeline = Pipeline(stages=[stage_0, stage_1])

        pipeline.disable_stage("Stage_1")

        assert pipeline.config.stages_to_run == {"Stage_0": True, "Stage_1": False}

    def test_enable_stage_restores_stage_in_explicit_mode(self, stage_factory) -> None:
        """
        Tests that when a stage is manually enabled in a Pipeline instance, it
        is correctly reflected in the stages_to_run configuration and the stage
        is included in the execution graph.
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1")
        pipeline = Pipeline(
            stages=[stage_0, stage_1],
            config=PipelineConfig(stages_to_run={"Stage_0": True, "Stage_1": False}),
        )

        pipeline.enable_stage("Stage_1")

        assert pipeline.config.stages_to_run["Stage_1"] is True
        assert {stage.name for stage in pipeline.graph.stages} == {"Stage_0", "Stage_1"}

    def test_add_stage_keeps_new_stage_out_of_explicit_selection(
        self, stage_factory
    ) -> None:
        """
        Tests that when a new stage is added to a Pipeline instance, it is
        kept out of the explicit selection.
        """
        stage_0 = stage_factory("Stage_0")
        pipeline = Pipeline(
            stages=[stage_0],
            config=PipelineConfig(stages_to_run={"Stage_0": True}),
        )

        pipeline.add_stage(
            stage_factory("Stage_1"),
            stage_configs=[StageConfig(name="Stage_1")]
            )
        

        assert pipeline.config.stages_to_run["Stage_1"] is False
        assert [stage.name for stage in pipeline.graph.stages] == ["Stage_0"]

    def test_add_stage_adds_new_stage_to_explicit_selection_when_enable_stages_is_true(
        self,
        stage_factory,
    ) -> None:
        """
        Tests that when a new stage is added to a Pipeline instance with
        enable_stages=True, it is included in the explicit selection.
        """
        stage_0 = stage_factory("Stage_0")
        pipeline = Pipeline(
            stages=[stage_0],
            config=PipelineConfig(stages_to_run={"Stage_0": True}),
        )

        pipeline.add_stage(
            stage_factory("Stage_1"),
            stage_configs=[StageConfig(name="Stage_1")],
            enable_stages=True,
        )

        assert pipeline.config.stages_to_run["Stage_1"] is True
        assert {stage.name for stage in pipeline.graph.stages} == {"Stage_0", "Stage_1"}


class TestPipelineValidationAndManifest:
    def test_validate_skips_source_check_for_disabled_stages(
        self, tmp_path: Path
    ) -> None:
        """
        Disabled stages' source files need not exist - validate() only checks the
        effective run set.
        """
        enabled_file = tmp_path / "Stage_0.py"
        enabled_file.write_text("def run(ctx): pass\n", encoding="utf-8")

        stage_0 = Stage("Stage_0", source=enabled_file)
        stage_1 = Stage(
            "Stage_1", source=tmp_path / "missing.py"
        )  # file intentionally absent

        pipeline = Pipeline(
            stages=[stage_0, stage_1],
            config=PipelineConfig(stages_to_run={"Stage_0": True, "Stage_1": False}),
        )

        pipeline.validate()  # must not raise

    def test_construct_manifest_inputs_contains_only_effective_stages(
        self, stage_factory
    ) -> None:
        """
        Manifest inputs should list only the stages that are part of the execution
        graph.
        """
        stage_0 = stage_factory("Stage_0")
        stage_1 = stage_factory("Stage_1", dependencies=("Stage_0",))
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