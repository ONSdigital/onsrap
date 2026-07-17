import yaml
from onsrap import Pipeline, PipelineConfig, StageConfig




def main() -> None:
    config = yaml.safe_load(open("conf.yaml"))

    Pipeline.from_config(config)

if __name__ == "__main__":
    main()