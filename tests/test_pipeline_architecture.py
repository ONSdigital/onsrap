from __future__ import annotations

from pathlib import Path
from textwrap import dedent

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
    )

    run = pipeline.run()

    assert run.succeeded is True
    assert [result.name for result in run.stage_results] == ["first_stage", "second_stage"]
    assert run.stage_outputs == {"first_stage": "alpha", "second_stage": "alpha-beta"}


def test_pipeline_falls_back_to_subprocess_for_plain_python_scripts(tmp_path: Path) -> None:
    script_stage = tmp_path / "script_stage.py"
    script_stage.write_text("print('script fallback works')\n", encoding="utf-8")

    pipeline = Pipeline.from_files([script_stage], name="script-pipeline")
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