from pathlib import Path
from textwrap import dedent

import pytest

from onsrap.stage import Stage, StageConfigurationError, _normalize_dependencies


class TestNormalizeDependencies:
    def test_normalize_dependencies_none(self) -> None:
        """
        Tests that None values return empty tuple.
        """
        assert _normalize_dependencies(None) == ()

    def test_normalize_dependencies_str(self) -> None:
        """
        Tests single string and list of string values including
        where whitespace appears before and after main text body
        """
        assert _normalize_dependencies("stage_1.py") == ("stage_1.py",)
        assert _normalize_dependencies("   stage_1.py") == ("stage_1.py",)
        assert _normalize_dependencies(
            ["Stage_1.py", "   Stage_2.py", "Stage_3.py   "]
        ) == ("Stage_1.py", "Stage_2.py", "Stage_3.py")


@pytest.fixture
def example_function():
    """
    Test function to pass as a callable stage for stage testing.
    """
    pass


@pytest.fixture
def stage_test() -> Stage:
    """
    Stage object for testing Stage class methods and construction.
    """
    return Stage("callable_stage", example_function, ["stage_1"], {"info": "example"})


class TestStage:
    def test_stage_creation_callable(self, stage_test) -> None:
        """
        Tests that attributes have been appropriately assigned to Stage class.

        Parameter
        ---------
        stage_test : Stage
            A ``Stage`` object created with a callable source for testing.
        """
        assert stage_test.name == "callable_stage"
        assert stage_test.source == example_function
        assert stage_test.dependencies == ("stage_1",)
        assert stage_test.metadata == {"info": "example"}
        assert stage_test.entrypoint is None
        assert stage_test.backend == "python"

    def test_stage_name_error(self, example_function) -> None:
        """
        Tests that a StageConfigurationError is raised if the name is left blank
        in a Stage class instance.

        Parameters
        ----------
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.

        Raises
        ------
        ``StageConfigurationError``
            If the name is left blank in a ``Stage`` class instance. 
        """
        with pytest.raises(StageConfigurationError):
            Stage("", example_function, ["stage_1"], {"info": "example"})

    def test_stage_source_type(self) -> None:
        """
        Tests that a non-valid source type returns a StageConfigurationError.

        Raises
        ------
        ``StageConfigurationError``
            If the source is not a valid callable or file path in a ``Stage`` class 
            instance.
        """
        with pytest.raises(StageConfigurationError):
            Stage("callable_stage", 11, ["stage_1"], {"info": "example"})

    def test_stage_backend(self, example_function) -> None:
        """
        Tests that backend can be any string, None, and corrects for whitespace.

        Parameters
        ----------
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.
        """
        stage_diff = Stage(
            "callable_stage",
            example_function,
            ["stage_1"],
            {"info": "example"},
            backend="java",
        )
        stage = Stage(
            "callable_stage",
            example_function,
            ["stage_1"],
            {"info": "example"},
            backend="",
        )
        stage_white_space = Stage(
            "callable_stage",
            example_function,
            ["stage_1"],
            {"info": "example"},
            backend="python   ",
        )
        assert stage_diff.backend == "java"
        assert stage.backend == "python"
        assert stage_white_space.backend == "python"

    def test_stage_from_files_error(self, tmp_path: Path) -> None:
        """
        Tests that if the file doesn't exist, a StageConfigurationError is raised.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary path provided by pytest for testing file creation and 
            manipulation.
        
        Raises
        ------
        ``StageConfigurationError``
            If the source file doesn't exist when attempting to create a 
            ``Stage`` instance
        """
        source_file = tmp_path / "not_an_actual_file.py"
        with pytest.raises(StageConfigurationError):
            Stage.from_file(source_file)

    def test_stage_from_callable_name(self, example_function) -> None:
        """
        Tests that a stage name is extracted from a callable object stage.

        Parameters
        ----------
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.
        """
        test = Stage.from_callable(example_function)
        assert test.name == "example_function"

    def test_from_dict_norm(self, example_function) -> None:
        """
        Tests that a stage instance is created from a dictionary item.

        Parameters
        ----------
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.
        """

        data = {"name": "test_Stage", "callable": example_function}
        stage = Stage.from_dict(data)
        assert stage.source == example_function

    def test_with_dependencies_list(self, stage_test) -> None:
        """
        Tests adding different types of dependencies when the original dependency is
        a list.

        Parameters
        ----------
        ``stage_test`` : Stage
            A ``Stage`` object created with a callable source for testing.
        """
        new_deps = ["stage2", "stage3"]
        new_deps_blank = []
        stage_test_list = stage_test.with_dependencies(new_deps)
        stage_test_blank = stage_test.with_dependencies(new_deps_blank)
        assert stage_test_list.dependencies == ("stage_1", "stage2", "stage3")
        assert stage_test_blank.dependencies == ("stage_1",)
        stage_test = stage_test.with_dependencies("stage2", "stage3")
        assert stage_test.dependencies == ("stage_1", "stage2", "stage3")

    def test_validate(self, stage_test, tmp_path) -> None:
        """
        Tests whether an error is raised if the source file isn't suitable.

        Parameters
        ----------
        ``stage_test`` : Stage
            A ``Stage`` object created with a callable source for testing.
        ``tmp_path`` : Path
            A temporary path provided by pytest for testing file creation and 
            manipulation.

        Raises
        ------
        ``StageConfigurationError``
            If the source is not a valid callable or file path in a ``Stage`` class 
            instance. In this instance, it raises if the source is None, an empty
            string, or a Path object that is not a file.
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

    def test_source_path(self, stage_test, tmp_path, example_function) -> None:
        """
        Tests whether source_path detects a path vs other valid and invalid source 
        types.

        Parameters
        ----------
        ``stage_test`` : Stage
            A ``Stage`` object created with a callable source for testing.
        ``tmp_path`` : Path
            A temporary path provided by pytest for testing file creation and 
            manipulation.
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.
        """
        stage_test.source = tmp_path / "fake_file.py"
        assert stage_test.source_path == tmp_path / "fake_file.py"
        stage_test.source = 11
        assert stage_test.source_path is None
        stage_test.source = "not a file path"
        assert stage_test.source_path is None
        stage_test.source = example_function
        assert stage_test.source_path is None

    def test_source_label(self, stage_test, tmp_path, example_function) -> None:
        """
        Tests that source_label is created if the source is a Path or a callable
        and is None if it is another type.

        Parameters
        ----------
        ``stage_test`` : Stage
            A ``Stage`` object created with a callable source for testing.
        ``tmp_path`` : Path
            A temporary path provided by pytest for testing file creation and 
            manipulation.
        ``example_function`` : callable
            A callable function to pass as a source for a ``Stage`` class instance.
        """
        stage_test.source = tmp_path / "fake_file.py"
        temp_path_str = str(tmp_path / "fake_file.py")
        assert stage_test.source_label == temp_path_str

        stage_test.source = example_function
        assert stage_test.source_label == "tests.test_stage.example_function"

        stage_test.source = 11
        assert stage_test.source_label is None


"""
TEST NOT CODED FOR RUN() AS ASSUMED THIS IS COVERED IN PIPELINE_ARCHITECTURE TEST
"""


class TestStageFactories:
    def test_stage_instance_from_file(self, tmp_path) -> None:
        """
        Tests that a Stage instance is created from a filepath.

        Parameters
        ----------
        ``tmp_path`` : Path
            A temporary path provided by pytest for testing file creation and 
            manipulation.
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

        assert Stage.from_file(test_stage, entrypoint="main") == Stage(
            "test_stage", test_stage.resolve(), (), {}, "main", "python"
        )
