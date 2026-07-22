import yaml
from onsrap import Pipeline, PipelineConfig, StageConfig
from pathlib import Path




def main() -> None:
    config_path = (Path(__file__).resolve().parent)/"conf.yaml"
    print(config_path)

    pipeline = Pipeline.from_config(config_path)

    run = pipeline.run()
    report = run.manifest.outputs
    print(report)

    print(f"Pipeline '{run.manifest.rap_name}' completed with {len(run.stage_results)} stages.")
    print(f"Summary report written to: {pipeline.config.output_dir}")
    print(f"Cleaned data written to: {pipeline.config.data_dir}")

if __name__ == "__main__":
    main()