from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from .errors import StageConfigurationError, StageLoadError

PREFERRED_ENTRYPOINTS = ("run", "main", "execute")


def discover_python_entrypoint(path: Path) -> str | None:
    file_path = Path(path)
    if not file_path.exists():
        raise StageConfigurationError("Stage source file does not exist: {0}".format(file_path))

    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, SyntaxError) as exc:
        raise StageConfigurationError(
            "Unable to inspect Python stage file {0}: {1}".format(file_path, exc)
        ) from exc

    defined_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for candidate in PREFERRED_ENTRYPOINTS:
        if candidate in defined_functions:
            return candidate

    return None


def load_python_callable(path: Path, entrypoint: str):
    module = load_python_module(path)
    target = getattr(module, entrypoint, None)
    if not callable(target):
        raise StageConfigurationError(
            "Entry point '{0}' was not callable in '{1}'.".format(entrypoint, path)
        )

    return target


def load_python_module(path: Path) -> ModuleType:
    file_path = Path(path)
    if not file_path.exists():
        raise StageLoadError("Stage source file does not exist: {0}".format(file_path))

    module_name = "onsrap_stage_{0}_{1}".format(
        file_path.stem,
        hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()[:12],
    )
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise StageLoadError("Unable to create a module spec for {0}".format(file_path))

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise StageLoadError(
            "Failed to import Python stage file {0}: {1}".format(file_path, exc)
        ) from exc

    return module
