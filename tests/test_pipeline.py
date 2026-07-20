from onsrap.pipeline import Pipeline, PipelineConfig
from onsrap.errors import PipelineInitialisationError
from onsrap.stage import Stage
from pathlib import Path
import pytest

def test_pipeline_name():
    """
    Test to confirm that Pipeline instance uses either defined name from 
    instance creation (shown in pipeline_named), utilises name from PipelineConfig
    if no name was given (shown in pipeline_config), or defaults to "pipeline" if
    no name is provided through Pipeline instance creation or through the 
    PipelineConfig (shown through pipeline_no_name)
    """
    pipeline_config = PipelineConfig(name = "test_pipeline_config")
    pipeline_named = Pipeline(name = "test_pipeline_name")
    assert pipeline_named.name == "test_pipeline_name"
    pipeline_config = Pipeline(name = None, config = pipeline_config)
    assert pipeline_config.name == "test_pipeline_config"
    pipeline_no_name = Pipeline()
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
    dependencies_single = {"Stage_2":("Stage_1",)}
    dependencies_multiple = {"Stage_1":["Stage_0", "Stage_0.5"],
                             "Stage_2":("Stage_1",)}
    dependencies_non_stage_name = {"Stage_1.py":("Stage_0",),
                                   "example_function":("Stage_1.py",)}
    
    with pytest.raises(PipelineInitialisationError):
        Pipeline(stages = None,
                 dependencies = dependencies_single)
    
    path = tmp_path/"Stage_1.py"
    pipeline_1 = Pipeline(name = "pipeline_1",
                          stages = [Stage("Stage_1", path, None,{}), 
                                    Stage("Stage_2", example_function, None,{})],
                          dependencies = dependencies_multiple)
    
    assert pipeline_1.stages[0].dependencies == ("Stage_0","Stage_0.5",)
    assert pipeline_1.stages[1].dependencies == ("Stage_1",)

    pipeline_2 = Pipeline(name = "pipeline_2",
                          stages = [Stage("Stage_1", path, None,{}), 
                                    Stage("Stage_2", example_function, None,{})],
                          dependencies = dependencies_non_stage_name)
    
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


    