import pytest
from onsrap.stage import _normalize_dependencies, Stage, StageConfigurationError
from pathlib import Path
from textwrap import dedent

def test_normalize_dependencies_none() -> None:
    """
    Tests that None values return empty tuple.
    """
    assert _normalize_dependencies(None) == ()

def test_normalize_dependencies_str() -> None:
    """
    Tests single string and list of string values including
    where whitespace appears before and after main text body
    """
    assert _normalize_dependencies("stage_1.py") == ("stage_1.py",)
    assert _normalize_dependencies("   stage_1.py") == ("stage_1.py",)
    assert _normalize_dependencies(
        ["Stage_1.py","   Stage_2.py", "Stage_3.py   "]
        ) == ("Stage_1.py","Stage_2.py", "Stage_3.py")

@pytest.fixture
def example_function():
    """
    Test function to pass as a callable stage for stage testing.
    """
    print("This is a test function")

@pytest.fixture
def stage_test() -> Stage:
    """
    Stage object for testing Stage class methods and construction. 
    """
    return Stage("callable_stage",example_function,["stage_1"],{"info":"example"})

def test_stage_creation_callable(stage_test) -> None:
    """
    Tests that attributes have been appropriately assigned to Stage class.
    """
    assert stage_test.name == "callable_stage"
    assert stage_test.source == example_function
    assert stage_test.dependencies == ("stage_1",)
    assert stage_test.metadata == {"info":"example"}
    assert stage_test.entrypoint == None
    assert stage_test.backend == "python"

def test_stage_name_error(example_function) -> None:
    """
    Tests that a StageConfigurationError is raised if the name is left blank
    in a Stage class instance.
    """
    with pytest.raises(StageConfigurationError):
        stage = Stage("",example_function,["stage_1"],{"info":"example"})

def test_stage_source_type() -> None: 
    """
    Tests that a non-valid source type returns a StageConfigurationError.
    """
    with pytest.raises(StageConfigurationError):
        stage = Stage("callable_stage",11,["stage_1"],{"info":"example"})

def test_stage_backend(example_function) -> None: 
    """
    Tests that backend can be any string, None, and corrects for whitespace.
    """
    stage_diff = Stage("callable_stage",example_function,["stage_1"],
                    {"info":"example"}, backend = "java")
    stage = Stage("callable_stage",example_function,["stage_1"],
                {"info":"example"}, backend = "")
    stage_white_space = Stage("callable_stage", example_function,["stage_1"],
                            {"info":"example"}, backend = "python   ")
    assert stage_diff.backend == "java"
    assert stage.backend == "python"
    assert stage_white_space.backend == "python"

def test_stage_from_files_error(tmp_path: Path) -> None:
    """
    Tests that if the file doesn't exist, a StageConfigurationError is raised.
    """
    source_file = tmp_path / "not_an_actual_file.py"
    with pytest.raises(StageConfigurationError):
        stage = Stage.from_file(source_file)

def test_stage_from_callable_name() -> None: 
    """
    Tests that a stage name is extracted from a callable object stage. 
    """
    def example_function():
        pass
    test = Stage.from_callable(example_function)
    assert test.name == "example_function"

def test_from_dict_norm() -> None:
    """
    Tests that a stage instance is created from a dictionary item. 
    """
    def example_function():
        pass
    data = {"name":"test_Stage",
            "callable" : example_function}
    stage = Stage.from_dict(data)
    assert stage.source == example_function

def test_with_dependencies_list(stage_test) -> None:
    """
    Tests adding different types of dependencies when the original dependency is
    a list. 
    """
    new_deps = ["stage2","stage3"]
    new_deps_blank = []
    stage_test_list = stage_test.with_dependencies(new_deps)
    stage_test_blank = stage_test.with_dependencies(new_deps_blank)
    assert stage_test_list.dependencies == ("stage_1",'stage2', 'stage3')
    assert stage_test_blank.dependencies == ("stage_1", )
    stage_test = stage_test.with_dependencies("stage2","stage3")
    assert stage_test.dependencies == ("stage_1",'stage2', 'stage3')


def test_validate(stage_test, tmp_path) -> None: 
    """
    Tests whether an error is raised if the source file isn't suitable. 
    """
    stage_test.source = None
    with pytest.raises(StageConfigurationError):
        stage_test.validate()
    not_file_path = tmp_path
    stage_test.source = not_file_path
    with pytest.raises(StageConfigurationError):
        stage_test.validate()
    stage_test.source = ""
    with pytest.raises(StageConfigurationError):
        stage_test.validate()

def test_source_path(stage_test, tmp_path) -> None: 
    """
    Tests whether source_path detects a path vs other valid and invalid source types.
    """
    stage_test.source = tmp_path/"fake_file.py"
    assert stage_test.source_path == tmp_path/"fake_file.py"
    stage_test.source = 11
    assert stage_test.source_path == None
    stage_test.source = "not a file path"
    assert stage_test.source_path == None

    def example_function():
        pass
    stage_test.source = example_function
    assert stage_test.source_path == None
    
def test_source_label(stage_test, tmp_path) -> None: 
    """
    Tests that source_label is created if the source is a Path or a callable and is None if it is
    another type. 
    """
    stage_test.source = tmp_path/"fake_file.py"
    temp_path_str = str(tmp_path/"fake_file.py")
    assert stage_test.source_label == temp_path_str

    def example_function():
        pass
    stage_test.source = example_function
    assert stage_test.source_label == "tests.test_stage.example_function"

    stage_test.source = 11
    assert stage_test.source_label == None

"""
TEST NOT CODED FOR RUN() AS ASSUMED THIS IS COVERED IN PIPELINE_ARCHITECTURE TEST
"""

def test_stage_instance_from_file(tmp_path) -> None:
    """
    Tests that a Stage instance is created from a filepath. 
    """
    test_stage = tmp_path / "test_stage.py"
    test_stage.write_text(
        dedent(
            """
            def main():
                variable = "Hello world"
                return variable
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    assert Stage.from_file(test_stage,
                           entrypoint = "main") == Stage("test_stage",
                                            test_stage.resolve(),
                                            (),
                                            {},
                                            "main",
                                            "python")
    
