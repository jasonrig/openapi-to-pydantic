"""Shared helpers for fixture-driven tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "openapi_specs"
_P = ParamSpec("_P")
_R = TypeVar("_R")


def fixture_dir() -> Path:
    """Return the OpenAPI fixtures directory."""
    return _FIXTURE_DIR


def iter_fixture_paths() -> list[Path]:
    """Return all YAML fixture paths sorted by name."""
    paths = sorted(_FIXTURE_DIR.glob("*.yaml")) + sorted(_FIXTURE_DIR.glob("*.yml"))
    return [path for path in paths if path.is_file()]


def parametrize_fixtures() -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Parametrize a test over all fixture paths."""

    def _decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        decorator: Callable[[Callable[_P, _R]], Callable[_P, _R]]
        decorator = pytest.mark.parametrize(
            "fixture_path",
            iter_fixture_paths(),
            ids=lambda path: path.name,
        )
        return decorator(func)

    return _decorator
