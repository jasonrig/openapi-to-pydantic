"""Fixture-based OpenAPI validation tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from openapi_python_client.schema import OpenAPI
from pydantic import ValidationError

from .fixture_helpers import fixture_dir, parametrize_fixtures

FIXTURE_DIR = fixture_dir()


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        pytest.fail(f"Failed to parse YAML in {path}: {exc}")
    except OSError as exc:
        pytest.fail(f"Failed to read fixture {path}: {exc}")

    if not isinstance(data, dict):
        pytest.fail(f"Fixture {path} must parse to a mapping, got {type(data)!r}")

    return cast(dict[str, Any], data)


def test_fixture_directory_exists() -> None:
    """Ensure the fixtures directory is present."""
    assert FIXTURE_DIR.is_dir(), f"Fixture directory not found: {FIXTURE_DIR}"


@parametrize_fixtures()
def test_fixture_is_valid_openapi(fixture_path: Path) -> None:
    """Validate each fixture using openapi-python-client's OpenAPI schema model."""
    data = _load_yaml(fixture_path)
    try:
        OpenAPI.model_validate(data)
    except ValidationError as exc:
        pytest.fail(f"OpenAPI validation failed for {fixture_path}:\n{exc}")
