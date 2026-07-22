from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from onsrap.errors import StageConfigurationError
from onsrap.graph import StageGraph
from onsrap.pipeline import Pipeline
from onsrap.stage import Stage


def test_pipeline_from_files_executes_python_entrypoints(tmp_path: Path) -> None:
    first_stage = tmp_path / "first_stage.py"
    first_stage.write_text(
        dedent(
            """
            def run(context):
                return "alpha"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    second_stage = tmp_path / "second_stage.py"
    second_stage.write_text(
        dedent(
            """
            def main(context):
                return context.result_for("first_stage").outputs + "-beta"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    pipeline = Pipeline.from_files(
        [first_stage, second_stage],
        dependencies={"second_stage": ("first_stage",)},
        config={"pipeline_config":{"work_dir": tmp_path,
                                    "project_root": tmp_path,
                                    "log_dir": tmp_path / "logs"},
                "stage_configuration": {}
        },
    )

    run = pipeline.run()

    assert run.succeeded is True
    assert [result.name for result in run.stage_results] == ["first_stage", "second_stage"]
    assert run.stage_outputs == {"first_stage": "alpha", "second_stage": "alpha-beta"}


def test_pipeline_uses_run_specific_output_directory(tmp_path: Path) -> None:
    writer_stage = tmp_path / "writer_stage.py"
    writer_stage.write_text(
        dedent(
            """
            from pathlib import Path

            def main(context):
                output_path = Path(context.run_dir) / "data" / "interim" / "artifact.txt"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(context.run_id, encoding="utf-8")
                return {"output_path": str(output_path), "run_id": context.run_id}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    pipeline = Pipeline.from_files(
        [writer_stage],
        config={"pipeline_config":{"work_dir": tmp_path,
                                    "project_root": tmp_path,
                                    "log_dir": tmp_path / "logs"},
                "stage_configuration": {}},
    )

    first_run = pipeline.run()
    second_run = pipeline.run()

    first_output = Path(first_run.stage_outputs["writer_stage"]["output_path"])
    second_output = Path(second_run.stage_outputs["writer_stage"]["output_path"])

    assert first_run.manifest.run_id != second_run.manifest.run_id
    assert first_output != second_output
    assert first_output.exists()
    assert second_output.exists()
    assert first_output.parents[2].name == first_run.manifest.run_id
    assert second_output.parents[2].name == second_run.manifest.run_id


def test_pipeline_falls_back_to_subprocess_for_plain_python_scripts(tmp_path: Path) -> None:
    script_stage = tmp_path / "script_stage.py"
    script_stage.write_text("print('script fallback works')\n", encoding="utf-8")

    pipeline = Pipeline.from_files(
        [script_stage],
        name="script-pipeline",
        config={"pipeline_config":{"work_dir": tmp_path,
                                    "project_root": tmp_path,
                                    "log_dir": tmp_path / "logs"},
                "stage_configuration": {}},
    )
    run = pipeline.run()

    assert run.stage_results[0].outputs.strip() == "script fallback works"
    assert run.stage_results[0].stdout.strip() == "script fallback works"


def test_stage_graph_detects_cycles() -> None:
    first_stage = Stage(name="first_stage", source=lambda context: None, dependencies=("second_stage",))
    second_stage = Stage(name="second_stage", source=lambda context: None, dependencies=("first_stage",))

    graph = StageGraph.from_stages([first_stage, second_stage])

    try:
        graph.topological_order()
    except Exception as exc:  # noqa: BLE001
        assert exc.__class__.__name__ == "DependencyCycleError"
    else:
        raise AssertionError("Expected a dependency cycle error")


def test_pipeline_from_config_builds_stages_and_injects_stage_config(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    stage_file = scripts_dir / "0_data_validation.py"
    stage_file.write_text(
        dedent(
            """
            def run(context):
                return {
                    "stage_name": context.stage_config.name,
                    "years_to_run": context.stage_config.get("years_to_run"),
                    "target_variable": context.stage_config.require("target_variable"),
                }
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    config_file = tmp_path / "conf.yaml"
    config_file.write_text(
        dedent(
            f"""
            pipeline_variables:
              name: "configured-pipeline"
              backend: python
              working_dir: "{tmp_path.as_posix()}"
              project_root: "{tmp_path.as_posix()}"
              log_dir: "{(tmp_path / 'logs').as_posix()}"
              stages:
                - 0_data_validation:
                    location: "{(tmp_path / 'scripts' / '0_data_validation.py').as_posix()}"
                    run: true
                    dependencies: []

            stage_configuration:
              0_data_validation:
                years_to_run: 2017
                target_variable: "classification"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    pipeline = Pipeline.from_config(config_file)

    #TODO: Fix above line of code. _split_config method is running twice when runs through from_config as it is called 
    #as part of the __init__ and part of the from_dict() that from_config() calls. Need to review how to normalise.

    assert [stage.name for stage in pipeline.stages] == ["0_data_validation"]
    assert pipeline.stage_configs["0_data_validation"].get("years_to_run") == 2017

    run = pipeline.run()

    assert run.stage_outputs["0_data_validation"] == {
        "stage_name": "0_data_validation",
        "years_to_run": 2017,
        "target_variable": "classification",
    }


def test_pipeline_rejects_unknown_stage_configuration(tmp_path: Path) -> None:
    stage_file = tmp_path / "single_stage.py"
    stage_file.write_text(
        dedent(
            """
            def run(context):
                return "ok"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    pipeline = Pipeline.from_files(
        [stage_file],
        config={"pipeline_config":{"work_dir": tmp_path,
                                    "project_root": tmp_path,
                                    "log_dir": tmp_path / "logs"},
            "stage_configuration": {
                "missing_stage": {"years_to_run": 2017},
            },
        },
    )

    with pytest.raises(StageConfigurationError, match="unknown stages"):
        pipeline.validate()


def test_pipeline_from_config_parses_stage_configuration_payloads(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    for stage_name in ("0_extract", "1_transform"):
        (scripts_dir / f"{stage_name}.py").write_text(
            dedent(
                """
                def run(context):
                    return context.stage_config.to_dict()
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    config_payload = {
        "pipeline_variables": {
            "name": "parse-test",
            "backend": "python",
            "working_dir": tmp_path.as_posix(),
            "project_root": tmp_path.as_posix(),
            "data_dir": (tmp_path / "data").as_posix(),
            "log_dir": (tmp_path / "logs").as_posix(),
            "metadata": {
                "description": "configuration parsing test",
            },
            "stages": [
                {
                    "0_extract": {
                        "location": "",
                        "run": True,
                        "dependencies": [],
                        "owner": "analytics",
                    }
                },
                {
                    "1_transform": {
                        "location": "",
                        "run": True,
                        "dependencies": ["0_extract"],
                    }
                },
            ],
        },
        "stage_configuration": {
            "0_extract": {
                "years_to_run": 2017,
                "datasets": {
                    "orders": {
                        "path": "data/orders.csv",
                    }
                },
                "metadata": {
                    "purpose": "extract",
                },
            },
            "1_transform": {
                "target_variable": "classification",
                "metadata": {
                    "purpose": "transform",
                },
            },
        },
    }

    config_file = tmp_path / "conf.yaml"
    config_file.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    pipeline = Pipeline.from_config(config_file)

    assert pipeline.name == "parse-test"
    assert pipeline.config.work_dir == tmp_path
    assert pipeline.config.project_root == tmp_path
    assert pipeline.config.log_dir == tmp_path / "logs"
    assert [stage.name for stage in pipeline.stages] == ["0_extract", "1_transform"]
    assert pipeline.stages[0].source_path == (scripts_dir / "0_extract.py").resolve()
    assert pipeline.stages[0].metadata["owner"] == "analytics"
    assert pipeline.stages[1].dependencies == ("0_extract",)
    assert pipeline.stage_configs["0_extract"].variables == {"years_to_run": 2017}
    assert pipeline.stage_configs["0_extract"].datasets == {"orders": {"path": "data/orders.csv"}}
    assert pipeline.stage_configs["0_extract"].metadata == {"purpose": "extract"}
    assert pipeline.create_stage_config(config_file, name="1_transform").require("target_variable") == "classification"


def test_pipeline_from_config_scales_stage_configuration_to_many_stages(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    stage_count = 6
    stage_names = [f"{index}_stage" for index in range(stage_count)]

    for index, stage_name in enumerate(stage_names):
        stage_file = scripts_dir / f"{stage_name}.py"
        previous_stage_name = stage_names[index - 1] if index > 0 else None
        stage_file.write_text(
            dedent(
                f"""
                def run(context):
                    previous_ordinal = None
                    if {index} > 0:
                        previous_ordinal = context.result_for("{previous_stage_name}").outputs["ordinal"]
                    return {{
                        "stage_name": context.stage_config.name,
                        "ordinal": context.stage_config.require("ordinal"),
                        "label": context.stage_config.require("label"),
                        "first_stage_ordinal": context.stage_config_for("{stage_names[0]}").require("ordinal"),
                        "known_stage_configs": sorted(context.stage_configs),
                        "previous_ordinal": previous_ordinal,
                    }}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    stage_definitions = []
    stage_configuration = {}
    for index, stage_name in enumerate(stage_names):
        dependencies = [stage_names[index - 1]] if index > 0 else []
        stage_definitions.append(
            {
                stage_name: {
                    "location": "",
                    "run": True,
                    "dependencies": dependencies,
                }
            }
        )
        stage_configuration[stage_name] = {
            "ordinal": index,
            "label": f"label-{index}",
        }

    config_file = tmp_path / "conf.yaml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "pipeline_variables": {
                    "name": "many-stage-pipeline",
                    "backend": "python",
                    "working_dir": tmp_path.as_posix(),
                    "project_root": tmp_path.as_posix(),
                    "log_dir": (tmp_path / "logs").as_posix(),
                    "stages": stage_definitions,
                },
                "stage_configuration": stage_configuration,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    pipeline = Pipeline.from_config(config_file)

    assert [stage.name for stage in pipeline.stages] == stage_names
    assert sorted(pipeline.stage_configs) == stage_names

    run = pipeline.run()

    assert run.manifest.stages_run == stage_names
    assert sorted(run.manifest.parameters["stage_configuration"]) == stage_names

    for index, stage_name in enumerate(stage_names):
        output = run.stage_outputs[stage_name]
        assert output["stage_name"] == stage_name
        assert output["ordinal"] == index
        assert output["label"] == f"label-{index}"
        assert output["first_stage_ordinal"] == 0
        assert output["known_stage_configs"] == stage_names
        expected_previous = None if index == 0 else index - 1
        assert output["previous_ordinal"] == expected_previous