"""Helpers for dynamically loading generated Python modules."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def load_module_from_path(*, module_name: str, module_path: Path) -> ModuleType:
    """Load a module from file path and register it in ``sys.modules``.

    Args:
        module_name (str): Temporary import name for the module.
        module_path (Path): File system path to the Python module.

    Returns:
        ModuleType: Imported Python module object.
    """
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module from: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module
