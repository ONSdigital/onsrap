import pytest

from pathlib import Path

import yaml

from onsrap.execution import ExecutionContext
from onsrap.logger import Logger
from onsrap.models import PipelineConfig, RunManifest
from onsrap.runner import _log_config


def test_log_config_writes_manifest_config_as_block_style_yaml(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "synthetic_run"
    run_dir.mkdir(parents=True)

    config = PipelineConfig(
        name="synthetic_pipeline",
        stages_to_run={"stage_a": True},
        backend="python",
        work_dir=tmp_path / "work",
        project_root=tmp_path,
        output_dir=tmp_path / "outputs",
        log_dir=tmp_path / "logs",
        data_dir=tmp_path / "data",
        allow_subprocess_fallback=True,
        python_executable=None,
        metadata={"reason": "unit test"},
    )

    context = ExecutionContext(
        pipeline_name="synthetic_pipeline",
        run_id="run_1234",
        config=config,
        logger=Logger(),
        run_dir=run_dir,
        started_at="2026-07-29_120000",
        working_directory=tmp_path,
        stage_configs={},
        global_config=None,
    )

    manifest_config = {
        "pipeline_config": {
            "name": "synthetic_pipeline",
            "backend": "python",
            "output_dir": str(tmp_path / "outputs"),
        },
        "stage_configs": {
            "stage_a": {
                "years_to_run": 2026,
                "target_variable": "classification",
            }
        },
        "global_config": {
            "dry_run": True,
        },
    }

    manifest = RunManifest(
        rap_name="synthetic_pipeline",
        run_id="run_1234",
        config=manifest_config,
    )

    _log_config(run_dir, context, manifest)

    expected_file = run_dir / (
        "configuration_for_"
        f"{context.pipeline_name}_{context.started_at}_{context.run_id}.yaml"
    )

    assert expected_file.exists()

    file_text = expected_file.read_text(encoding="utf-8")
    parsed_yaml = yaml.safe_load(file_text)

    assert parsed_yaml == manifest_config
    assert "stage_configs:\n" in file_text
    assert "  stage_a:\n" in file_text
    assert "    years_to_run: 2026\n" in file_text
    assert "pipeline_config: {" not in file_text
    assert "stage_configs: {" not in file_text
    assert "global_config: {" not in file_text