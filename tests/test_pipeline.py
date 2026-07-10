from onsrap.pipeline import Pipeline, PipelineConfig
import pytest

@pytest.fixture
def pipelineconfig() -> PipelineConfig:
    return PipelineConfig(name = "test_pipeline_config")

def test_pipeline_name(pipelineconfig):
    """
    Test to confirm that Pipeline instance uses either defined name from 
    instance creation (shown in pipeline_named), utilises name from PipelineConfig
    if no name was given (shown in pipeline_config), or defaults to "pipeline" if
    no name is provided through Pipeline instance creation or through the 
    PipelineConfig (shown through pipeline_no_name)
    """
    pipeline_named = Pipeline(name = "test_pipeline_name")
    assert pipeline_named.name == "test_pipeline_name"
    pipeline_config = Pipeline(name = None, config = pipelineconfig)
    assert pipeline_config.name == "test_pipeline_config"
    pipeline_no_name = Pipeline()
    assert pipeline_no_name.name == "pipeline"
    