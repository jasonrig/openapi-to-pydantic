"""Shared helpers for fixture-driven tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar, cast

import pytest

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "openapi_specs"
_F = TypeVar("_F", bound=Callable[..., object])


def fixture_dir() -> Path:
    """Return the OpenAPI fixtures directory."""
    return _FIXTURE_DIR


def iter_fixture_paths() -> list[Path]:
    """Return all YAML fixture paths sorted by name."""
    paths = sorted(_FIXTURE_DIR.glob("*.yaml")) + sorted(_FIXTURE_DIR.glob("*.yml"))
    return [path for path in paths if path.is_file()]


def parametrize_fixtures() -> Callable[[_F], _F]:
    """Parametrize a test over all fixture paths."""
    decorator = pytest.mark.parametrize(
        "fixture_path",
        iter_fixture_paths(),
        ids=lambda path: path.name,
    )
    return cast(Callable[[_F], _F], decorator)
